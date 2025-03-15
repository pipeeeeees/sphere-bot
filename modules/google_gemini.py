import requests

def get_gemini_response(message: str, api_key: str) -> str:
    """
    Sends a message to the Google Gemini API and returns the response.
    :param message: The input message.
    :param api_key: Your Google Gemini API key.
    :return: The response text if available, otherwise None.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": message}]}]
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        candidates = response.json().get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", None) if parts else None
    return None