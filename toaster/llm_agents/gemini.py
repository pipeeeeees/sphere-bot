import json
from pathlib import Path
from typing import Optional, Tuple
import asyncio

from google import genai
from google.genai import types

from toaster.llm_agents.agent_utils import get_default_system_prompt, build_conversation_snippet, build_is_this_reply_worthy_snippet


def get_gemini_response(history: str, message: str, api_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get a response from Google's Gemini AI model with web grounding.
    Uses gemini-2.5-flash for fast responses with up-to-date information.
    
    Args:
        history: Previous conversation history
        message: Current user message
        api_key: Gemini API key
        
    Returns:
        Tuple of (response text, error message) - response is None on error, error contains details
    """
    try:
        client = genai.Client(api_key=api_key)
        
        system_prompt = get_default_system_prompt()
        max_total_chars = 3000
        
        # Build conversation snippet with history and message
        conversation = build_conversation_snippet(history, message, max_total_chars)

        #print(conversation)
        
        # Combine system prompt with conversation
        full_prompt = f"{system_prompt}\n\n{conversation}"
        
        # Make request with Google Search grounding for current information
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=800
            )
        )
        
        # Return empty string for empty responses, None only for errors
        if response.text:
            return response.text, None
        else:
            return "", None
        
    except Exception as e:
        print(f"Error in Gemini API call: {e}")
        return None, str(e)


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


def get_gemini_response_with_key(history: str, message: str, config_path: str = "config") -> Tuple[Optional[str], Optional[str]]:
    """
    Convenience function that loads the API key and gets a Gemini response.
    
    Args:
        history: Previous conversation history
        message: Current user message  
        config_path: Path to config directory
        
    Returns:
        Tuple of (response text, error message)
    """
    api_key = load_gemini_key(config_path)
    if not api_key:
        return None, "Gemini API key not found in config/gemini_key.json"
    
    return get_gemini_response(history, message, api_key)

async def infer_if_reply_is_at_toast(history:str, message:str, api_key:str) -> bool:
    """
    Infer if the user's message is likely directed at Toast based on conversation history and message content.
    Uses a simple heuristic approach with the Gemini model to analyze the context.
    
    Args:
        history: Previous conversation history
        message: Current user message
        api_key: Gemini API key
    Returns:
        True if the message is likely directed at Toast, False otherwise
    """
    
    # Retry logic: try up to 3 times with exponential backoff
    for attempt in range(3):
        try:
            client = genai.Client(api_key=api_key)
            
            system_prompt = (
                "You are an assistant that determines if a user's message in a conversation is directed at Toast, a helpful Discord bot. "
                "Based on the conversation history and the final message, respond with 'Yes' if the final message (and prior context) prompt a reasonable reply from Toast, or 'No' if it is not."
            )
            
            max_total_chars = 1500
            conversation = build_is_this_reply_worthy_snippet(history, message, max_total_chars)
            full_prompt = f"{system_prompt}\n\nConversation history:\n{conversation}"
            
            #print(full_prompt)

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=50
                )
            )
            
            # Check if we got a valid response text
            if response.text:
                return response.text.strip().lower() == "yes"
            else:
                # No text in response, treat as failure
                raise Exception("Gemini API returned empty response text")
            
        except Exception as e:
            print(f"Error in Gemini API call for reply inference (attempt {attempt + 1}/3): {e}")
            if attempt < 2:  # Don't wait after the last attempt
                wait_time = 2 ** (attempt + 1)  # 2 seconds after first failure, 4 after second
                print(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
    
    # All attempts failed
    return False

if __name__ == "__main__":
    pass