"""
Shared utilities for LLM agent implementations.
"""

from typing import List


def get_default_system_prompt() -> str:
    """Default instruction for all Toast AI agents."""
    return (
        "Below is your prompt. You are Toast in this conversation (alias for the bot). "
        "Be concise and helpful. Keep answers under 1800 characters to fit Discord's message limit. Answer in the first person as Toast formatted for a discord message. No need to say hey just give your reply"
    )


def prune_history(history: str, max_chars: int) -> str:
    """Trim history from the oldest entries until within max character length."""
    if not history:
        return ""

    lines = history.strip().split("\n")
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text

    # Drop earliest lines until we fit
    while lines and len("\n".join(lines)) > max_chars:
        lines.pop(0)

    return "\n".join(lines)


def build_conversation_snippet(history: str, message: str, max_total_chars: int) -> str:
    """Create a single text snippet with history plus current message, within max_total_chars."""
    if not history:
        combined = message.strip()
        if len(combined) <= max_total_chars:
            return combined
        return combined[-max_total_chars:]

    # Reserve 20% of the budget for the current message (min 21 chars)
    budget_for_history = max_total_chars - max(21, int(len(message) * 0.2))
    pruned_history = prune_history(history, budget_for_history)
    reply_to = f"Reply to the following message: {message.strip()}"
    combined = f"{pruned_history}\n{reply_to}".strip()

    if len(combined) <= max_total_chars:
        return combined

    # Last resort, trim from the front
    return combined[-max_total_chars:]

def build_is_this_reply_worthy_snippet(history: str, message: str, max_total_chars: int) -> str:
    """Create a single text snippet with history plus current message, within max_total_chars."""
    if not history:
        combined = message.strip()
        if len(combined) <= max_total_chars:
            return combined
        return combined[-max_total_chars:]

    # Reserve 20% of the budget for the current message (min 21 chars)
    budget_for_history = max_total_chars - max(21, int(len(message) * 0.2))
    pruned_history = prune_history(history, budget_for_history)
    reply_to = f"Does this final message (and prior context) prompt a reasonable reply from Toast: {message.strip()}"
    combined = f"{pruned_history}\n{reply_to}".strip()

    if len(combined) <= max_total_chars:
        return combined

    # Last resort, trim from the front
    return combined[-max_total_chars:]


def build_grok_messages(history: str, message: str, max_length: int = 2000) -> List[dict]:
    """Build Grok message list with pruned history and system prompt."""
    system_prompt = get_default_system_prompt()
    history_snippet = build_conversation_snippet(history, message, max_length - len(system_prompt) - 20)

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Here is the message history for context from oldest to newest:\n\n"
                + (history_snippet + "\n" if history_snippet else "")
                + f"Reply to the following message in under {max_length} characters without telling me how many characters you used. Also do not add follow up questions:\n{message}"
            )
        }
    ]


def build_gemini_contents(history: str, message: str, max_history_chars: int = 1500) -> List[dict]:
    """Build Gemini API contents with pruned history and a default prompt."""
    contents = []
    system_prompt = get_default_system_prompt()
    contents.append({"role": "user", "parts": [{"text": system_prompt}]})

    history_snippet = prune_history(history, max_history_chars)
    if history_snippet:
        # Convert history lines into role-style entries (User/AI). Keep raw to preserve existing called formats.
        for line in history_snippet.split("\n"):
            if line.startswith("User: "):
                contents.append({"role": "user", "parts": [{"text": line[6:]}]})
            elif line.startswith("AI: ") or line.startswith("Assistant: "):
                contents.append({"role": "model", "parts": [{"text": line.split(": ", 1)[1]}]})
            else:
                contents.append({"role": "user", "parts": [{"text": line}]})

    contents.append({"role": "user", "parts": [{"text": message}]})
    return contents
