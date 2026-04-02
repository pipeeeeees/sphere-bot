import requests
import json
from pathlib import Path
from typing import Optional


def load_grok_key(config_path: str = "config") -> Optional[str]:
    """
    Load the Grok API key from config file.
    
    Args:
        config_path: Path to config directory
        
    Returns:
        API key string or None if not found
    """
    try:
        config_file = Path(config_path) / "grok_key.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
                return data.get("token")
        return None
    except Exception as e:
        print(f"Error loading Grok key: {e}")
        return None


def get_grok_response(history: str, message: str, api_key: str) -> Optional[str]:
    system_prompt = (
        "Hey, Grok. You're Sphere in this conversaion - just an alias."
        "Be concise. Just reply with the message content in under 2000 chars. Ideally in a sentence or two. Be chill"
    )

    max_length = 2000

    # Split history into individual messages
    history_lines = history.split("\n")

    def build_messages(hist_lines):
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Here is the message history for context from oldest to newest:\n\n"
                    + "\n".join(hist_lines)
                    + f"\n\nReply to the following message in under 2000 characters:\n{message}"
                )
            }
        ]

    messages = build_messages(history_lines)

    # Trim history if total prompt gets too long
    def total_length(msgs):
        return sum(len(m["content"]) for m in msgs)

    while total_length(messages) > max_length and history_lines:
        history_lines.pop(0)
        messages = build_messages(history_lines)

    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "grok-4-1-fast-reasoning",
        "messages": messages,
        "temperature": 0.9,
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0]["message"]["content"]

    return None


def get_grok_response_with_key(history: str, message: str, config_path: str = "config") -> Optional[str]:
    """
    Convenience function that loads the API key and gets a Grok response.
    
    Args:
        history: Previous conversation history
        message: Current user message  
        config_path: Path to config directory
        
    Returns:
        AI response text or None if error
    """
    api_key = load_grok_key(config_path)
    if not api_key:
        print("Grok API key not found in config/grok_key.json")
        return None
    
    return get_grok_response(history, message, api_key)