from pathlib import Path

from toast import build_person_memory_context, update_person_memory
from toaster.llm_agents.gemini import build_gemini_prompt


class DummyAuthor:
    def __init__(self, user_id, name):
        self.id = user_id
        self.name = name
        self.display_name = name


class DummyChannel:
    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name


class DummyMessage:
    def __init__(self, author, channel, content):
        self.author = author
        self.channel = channel
        self.content = content


def test_person_memory_is_persisted_and_referenced(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    message = DummyMessage(
        DummyAuthor(42, "Ava"),
        DummyChannel(99, "general"),
        "I love cats and I live in Seattle",
    )

    update_person_memory(message, config_dir=config_dir)

    memory_path = config_dir / "person_memory.json"
    assert memory_path.exists()

    context = build_person_memory_context(message, config_dir=config_dir)
    assert "Ava" in context
    assert "cats" in context.lower()
    assert "seattle" in context.lower()


def test_gemini_prompt_includes_personal_memory_context():
    prompt = build_gemini_prompt(
        history="[2026-07-13 18:20:00 UTC] User: hey",
        message="What do you think?",
        memory_context="Known about Ava from earlier messages:\n- loves cats",
    )

    assert "Personal context about the person" in prompt
    assert "loves cats" in prompt
    assert "What do you think?" in prompt


def test_person_memory_context_only_includes_relevant_people(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    memory = {
        "user_1": {
            "user_id": 1,
            "display_name": "Ava",
            "channels": [],
            "facts": ["loves cats"],
            "message_count": 1,
            "last_seen": None,
        },
        "user_2": {
            "user_id": 2,
            "display_name": "Ben",
            "channels": [],
            "facts": ["lives in Chicago"],
            "message_count": 1,
            "last_seen": None,
        },
        "user_3": {
            "user_id": 3,
            "display_name": "Charlie",
            "channels": [],
            "facts": ["hates Monday"],
            "message_count": 1,
            "last_seen": None,
        },
    }

    import json
    (config_dir / "person_memory.json").write_text(json.dumps(memory), encoding="utf-8")

    message = DummyMessage(DummyAuthor(42, "Drew"), DummyChannel(99, "general"), "Ava and Ben are talking about the weekend")
    context = build_person_memory_context(message, config_dir=config_dir, history_context="[2026-07-13 18:20:00 UTC] Ava: hi\n[2026-07-13 18:20:05 UTC] Ben: hello")

    assert "Ava" in context
    assert "Ben" in context
    assert "Charlie" not in context
