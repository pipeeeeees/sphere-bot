"""Config-driven Gemini trivia generation and question history."""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from toaster.llm_agents.gemini import get_gemini_response_with_key


CONFIG_FILE = Path("config/trivia_config.json")
HISTORY_FILE = Path("config/trivia_history.json")
DEFAULT_HISTORY_SIZE = 50


def load_trivia_config() -> dict:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        return config if isinstance(config, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _get_schedule(config: dict, default_name: str, command: str) -> Optional[dict]:
    schedule = config.get("schedule")
    if not config.get("enabled", True) or not isinstance(schedule, dict):
        return None
    return {
        "name": config.get("name", default_name),
        "message": command,
        "channel_id": config.get("channel_id"),
        "type": schedule.get("type", "weekly"),
        "time": schedule.get("time", "11:30"),
        "weekdays": schedule.get("weekdays", [1, 3, 5]),
        "date": schedule.get("date"),
        "timezone": schedule.get("timezone", "America/New_York"),
        "enabled": config.get("enabled", True),
    }


def _get_trivia_configs() -> list[dict]:
    config = load_trivia_config()
    entries = config.get("trivia")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    return [config] if config else []


def get_trivia_schedules() -> list[dict]:
    schedules = []
    for config in _get_trivia_configs():
        name = str(config.get("name", "trivia"))
        command = "$trivia_cfb" if name == "college_trivia" else "$trivia_mlb"
        schedule = _get_schedule(config, name, command)
        if schedule:
            schedules.append(schedule)
    return schedules


def get_trivia_schedule() -> Optional[dict]:
    """Backward-compatible accessor for the first configured trivia schedule."""
    schedules = get_trivia_schedules()
    return schedules[0] if schedules else None


def _load_history(history_file: Path = HISTORY_FILE) -> list[str]:
    try:
        with history_file.open("r", encoding="utf-8") as file:
            history = json.load(file)
        return [str(item) for item in history] if isinstance(history, list) else []
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []


def _save_history(history: list[str], limit: int, history_file: Path = HISTORY_FILE) -> None:
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with history_file.open("w", encoding="utf-8") as file:
            json.dump(history[-limit:], file, indent=2)
    except OSError:
        pass


def _clean_question(response: str) -> str:
    """Remove Gemini's optional conversational framing and answer section."""
    question = re.split(r"\bAnswer\s*:\s*", response, maxsplit=1, flags=re.IGNORECASE)[0]
    lines = [line.strip() for line in question.splitlines() if line.strip()]
    if not lines:
        return ""

    # If Gemini adds an intro on its own line, keep the first line containing
    # the actual question and everything following it.
    question_line = next((index for index, line in enumerate(lines) if "?" in line), 0)
    question = " ".join(lines[question_line:]).strip()
    question = re.sub(
        r"^(?:Sure|Sure thing|I can do that)[!,\s:.-]*(?:Here is a trivia question:)?\s*",
        "",
        question,
        flags=re.IGNORECASE,
    )
    return question.strip()


def _generate_trivia(config: dict, history: list[str]) -> str:
    topic = config.get("topic", "MLB trivia")
    recent_history = "\n".join(f"- {item}" for item in history[-50:]) or "(none)"
    prompt = (
        f"Create one challenging trivia question about {topic}.\n"
        "Return only the question. Do not provide the answer, an answer label, an introduction, or any other text. "
        "Do not use multiple choice. Do not repeat or closely paraphrase any recent question below.\n"
        f"Recent questions to avoid:\n{recent_history}"
    )
    response, error = get_gemini_response_with_key("", prompt)
    if not response:
        raise RuntimeError(error or "Gemini returned no trivia question")
    question = _clean_question(response.strip())
    if not question:
        raise RuntimeError("Gemini returned no usable trivia question")
    return f"Trivia time: {question}"


async def _generate_and_store(config: dict, history_file: Path) -> str:
    history = _load_history(history_file)
    limit = max(1, int(config.get("history_size", DEFAULT_HISTORY_SIZE)))
    for _ in range(3):
        trivia = await asyncio.to_thread(_generate_trivia, config, history)
        question_text = trivia.replace("Trivia time: ", "", 1)
        if question_text not in history:
            history.append(question_text)
            if history_file == HISTORY_FILE:
                _save_history(history, limit)
            else:
                _save_history(history, limit, history_file)
            return trivia
    raise RuntimeError("Gemini repeated a recent trivia question")


def _get_trivia_config(name: str) -> dict:
    config = load_trivia_config()
    if not isinstance(config.get("trivia"), list) and name == "mlb_trivia":
        return config
    return next(
        (config for config in _get_trivia_configs() if config.get("name") == name),
        {},
    )


async def generate_and_store_trivia() -> str:
    return await _generate_and_store(_get_trivia_config("mlb_trivia"), HISTORY_FILE)


async def generate_and_store_college_trivia() -> str:
    return await _generate_and_store(
        _get_trivia_config("college_trivia"),
        Path("config/college_trivia_history.json"),
    )


async def trivia_mlb_command(ctx) -> None:
    """Generate and post one configured trivia question."""
    try:
        await ctx.send(await generate_and_store_trivia())
    except Exception:
        await ctx.send("Trivia is currently unavailable. Please try again later.")


async def trivia_cfb_command(ctx) -> None:
    """Generate and post one configured college-football question."""
    try:
        await ctx.send(await generate_and_store_college_trivia())
    except Exception:
        await ctx.send("College football trivia is currently unavailable. Please try again later.")