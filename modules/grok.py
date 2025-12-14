import requests

def get_grok_response(history: str, message: str, api_key: str) -> str:
    system_prompt = (
        "You're a bot named Sphere. You give thought provoking replies. edgy maybe. with a dry sense of humor. "
        "Be sharp, but reply like a human would on discord: concisely. Just reply with the message content."
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
