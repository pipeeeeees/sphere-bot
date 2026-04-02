import requests
import json
from pathlib import Path
from typing import Optional

from toaster.llm_agents.agent_utils import build_grok_messages


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
    max_length = 2000
    messages = build_grok_messages(history, message, max_length)
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