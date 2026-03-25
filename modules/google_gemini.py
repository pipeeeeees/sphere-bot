import requests

def get_gemini_response(history: str, message: str, api_key: str) -> str:
    intro_message_base = (
        "youre a bot named Sphere and you give edgy and perhaps controversial replies. "
        "here is the message history for context from oldest to newest:\n\n"
    )
    message_part = (
        f"\n\nreply with just your reply to the following message in less than 2000 chars. "
        f"have fun with it: {message}"
    )

    history_lines = history.split("\n")
    current_history = history

    intro_message = intro_message_base + current_history + message_part
    max_length = 2000

    # Trim history if too long
    while len(intro_message) > max_length and history_lines:
        history_lines.pop(0)
        current_history = "\n".join(history_lines)
        intro_message = intro_message_base + current_history + message_part

    prompt = intro_message

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key}"

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 512,
            "temperature": 0.9
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None

        return parts[0].get("text", None)

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None