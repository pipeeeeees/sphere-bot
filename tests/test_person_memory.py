from pathlib import Path

from toast import build_person_memory_context, update_person_memory


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
