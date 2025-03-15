import requests

def get_gemini_response(history: str, message: str, api_key: str) -> str:

    intro_message = rf'Your name is "Sphere#1751". here is the message history for context from oldest to newest:\n\n{history}\n\nReply to this message with that context in mind. It may be useful or irrelevant: '
    prompt = intro_message + message

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        candidates = response.json().get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", None) if parts else None
    return None