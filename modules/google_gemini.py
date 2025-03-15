import requests

def get_gemini_response(history: str, message: str, api_key: str) -> str:
    intro_message_base = f'youre a discord bot named "Sphere#1751", Sphere for short. here is the message history for context from oldest to newest:\n\n'
    message_part = f"\n\nreply to the following message as Sphere: {message}"
    
    # Split history into individual messages
    history_lines = history.split("\n")
    
    # Start with full history and reduce if necessary
    current_history = history
    intro_message = intro_message_base + current_history + message_part
    max_length = 2000

    # Reduce history one line at a time from the oldest if over max_length
    while len(intro_message) > max_length and history_lines:
        history_lines.pop(0)  # Remove the oldest message
        current_history = "\n".join(history_lines)
        intro_message = intro_message_base + current_history + message_part

    prompt = intro_message

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