import os
import json
import requests
from typing import Optional
from pathlib import Path
import time

def get_gemini_response(history: str, message: str, api_key: str) -> Optional[str]:
    """
    Get a response from Google's Gemini AI model.
    
    Args:
        history: Previous conversation history
        message: Current user message
        api_key: Gemini API key
        
    Returns:
        AI response text or None if error
    """
    
    # Using v1 for gemini-2.0-flash (switching back after quota reset)
    # Note: v1 is stable API endpoint vs v1beta
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # Prepare the conversation history and current message
    contents = []
    
    # Add history if provided
    if history and history.strip():
        # Split history into turns (assuming format like "User: message\nAI: response\n")
        history_parts = history.strip().split('\n')
        for part in history_parts:
            if part.startswith('User: '):
                contents.append({
                    "role": "user",
                    "parts": [{"text": part[6:]}]  # Remove "User: " prefix
                })
            elif part.startswith('AI: ') or part.startswith('Assistant: '):
                contents.append({
                    "role": "model", 
                    "parts": [{"text": part[4:]}]  # Remove "AI: " prefix
                })
    
    # Add current message
    contents.append({
        "role": "user",
        "parts": [{"text": message}]
    })
    
    # Prepare the request payload
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024,
        }
    }
    
    try:
        # Make the API request with retry logic for rate limits
        headers = {
            'Content-Type': 'application/json'
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                response.raise_for_status()  # Raise exception for bad status codes
                break  # Success, exit retry loop
                
            except requests.exceptions.HTTPError as e:
                error_code = e.response.status_code if hasattr(e.response, 'status_code') else None
                error_body = e.response.text if hasattr(e.response, 'text') else ''
                
                if error_code == 429:
                    # Rate limit exceeded
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        print(f"Rate limit hit, waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"Rate limit persisted after {max_retries} attempts")
                        return None
                else:
                    # Other HTTP error
                    print(f"HTTP Error {error_code}: {error_body}")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                return None
        
        # Parse the response
        data = response.json()
        
        # Extract the generated text
        if 'candidates' in data and len(data['candidates']) > 0:
            candidate = data['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content']:
                parts = candidate['content']['parts']
                if len(parts) > 0 and 'text' in parts[0]:
                    return parts[0]['text'].strip()
        
        # If we can't extract text, return None
        return None
        
    except json.JSONDecodeError as e:
        print(f"Error parsing Gemini API response: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in Gemini API call: {e}")
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
    Standalone test for Gemini API integration.
    Run this file directly to test the API without running the full bot.
    """
    import sys
    
    print("🤖 Gemini API Test")
    print("=" * 50)
    
    # Load API key
    api_key = load_gemini_key()
    if not api_key:
        print("❌ No API key found in config/gemini_key.json")
        sys.exit(1)
    
    print(f"✓ API key loaded (ends with: ...{api_key[-10:]})")
    print(f"✓ Full key: {api_key}")
    print(f"✓ Model: gemini-1.5-flash (on stable v1 API)\n")
    
    # Test with simple message first
    print("🧪 Test 1: Simple greeting")
    print("-" * 30)
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key}"
    print(f"API Endpoint: {url}\n")
    
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": "Hello"}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024,
        }
    }
    
    headers = {'Content-Type': 'application/json'}
    
    print("Sending request...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body:\n{response.text}\n")
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data:
                print("✅ API is working!")
                print(f"Response: {data['candidates'][0]['content']['parts'][0]['text']}")
            else:
                print("❌ Unexpected response format")
        else:
            print(f"❌ API returned error code {response.status_code}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
    
    print("\n" + "=" * 50)
    print("🔍 Debugging Tips:")
    print("- If you see 'Invalid API Key': Generate new key from Google AI Studio")
    print("- If you see 'Resource not found': Enable Generative Language API")
    print("- If you see quota exceeded: Your free tier limit has been reached")
    print("  → Upgrade to paid plan at https://ai.google.dev/pricing")
    print("  → Free tier limits: 15 RPM (requests/min), 1000 RPD (requests/day)")
    print("- If key is empty: Check config/gemini_key.json exists and has 'key' field")
    print("\nℹ️  Note: Gemini 2.0 Flash free tier quota is very limited.")
    print("Consider using Gemini 1.5 Flash or upgrading to a paid plan.")
