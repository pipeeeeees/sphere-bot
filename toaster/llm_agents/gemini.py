import json
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from toaster.llm_agents.agent_utils import get_default_system_prompt, build_conversation_snippet


def get_gemini_response(history: str, message: str, api_key: str) -> Optional[str]:
    """
    Get a response from Google's Gemini AI model with web grounding.
    Uses gemini-2.5-flash for fast responses with up-to-date information.
    
    Args:
        history: Previous conversation history
        message: Current user message
        api_key: Gemini API key
        
    Returns:
        AI response text or None if error
    """
    try:
        client = genai.Client(api_key=api_key)
        
        system_prompt = get_default_system_prompt()
        max_total_chars = 3000
        
        # Build conversation snippet with history and message
        conversation = build_conversation_snippet(history, message, max_total_chars)
        
        # Combine system prompt with conversation
        full_prompt = f"{system_prompt}\n\n{conversation}"
        
        # Make request with Google Search grounding for current information
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
            max_output_tokens=500
        )
        
        return response.text.strip() if response.text else None
        
    except Exception as e:
        print(f"Error in Gemini API call: {e}")
        return None


def load_gemini_key(config_path: str = "config") -> Optional[str]:
    """
    Load the Gemini API key from config file.
    
    Args:
        config_path: Path to config directory
        
    Returns:
        API key string or None if not found
    """
    try:
        config_file = Path(config_path) / "gemini_key.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
                return data.get("key")
        return None
    except Exception as e:
        print(f"Error loading Gemini key: {e}")
        return None


def get_gemini_response_with_key(history: str, message: str, config_path: str = "config") -> Optional[str]:
    """
    Convenience function that loads the API key and gets a Gemini response.
    
    Args:
        history: Previous conversation history
        message: Current user message  
        config_path: Path to config directory
        
    Returns:
        AI response text or None if error
    """
    api_key = load_gemini_key(config_path)
    if not api_key:
        print("Gemini API key not found in config/gemini_key.json")
        return None
    
    return get_gemini_response(history, message, api_key)


if __name__ == "__main__":
    """
    Standalone test for Gemini API integration with grounding.
    Run this file directly to test the API without running the full bot.
    """
    import sys
    
    print("🤖 Gemini API Test (with Web Grounding)")
    print("=" * 50)
    
    # Load API key
    api_key = load_gemini_key()
    if not api_key:
        print("❌ No API key found in config/gemini_key.json")
        sys.exit(1)
    
    print(f"✓ API key loaded (ends with: ...{api_key[-10:]})")
    print(f"✓ Model: gemini-2.5-flash (with Google Search grounding)\n")
    
    # Test with a simple message
    print("🧪 Test: Simple greeting")
    print("-" * 30)
    
    test_message = "Hello! What's a recent tech news story?"
    print(f"Sending: {test_message}")
    print()
    
    response = get_gemini_response_with_key("", test_message)
    
    if response:
        print("✅ API is working!")
        print(f"Response:\n{response}")
    else:
        print("❌ API failed to return a response")
    
    print("\n" + "=" * 50)
    print("Note: Gemini 2.5 Flash with grounding provides up-to-date information.")
