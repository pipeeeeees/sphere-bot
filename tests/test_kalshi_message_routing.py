import asyncio
from types import SimpleNamespace

import pytest

from toast import handle_kalshi_game_message


class DummyChannel:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


class DummyAuthor:
    def __init__(self):
        self.id = 123
        self.display_name = "Test User"
        self.name = "Test User"


class DummyMessage:
    def __init__(self):
        self.author = DummyAuthor()
        self.content = "hey toast https://kalshi.com/markets/kxwcadvance/world-cup-advance/kxwcadvance-26jul14fraesp give me $1000 on spain"
        self.channel = DummyChannel()
        self.guild = None
        self.embeds = []
        self.attachments = []


@pytest.mark.asyncio
async def test_kalshi_handler_short_circuits_and_sends_bet_reply(monkeypatch):
    message = DummyMessage()

    async def fake_save_state(state):
        return None

    monkeypatch.setattr("toast.save_state", fake_save_state)
    monkeypatch.setattr("toast.load_state", lambda: {"users": {}})

    handled = await handle_kalshi_game_message(message)

    assert handled is True
    assert message.channel.sent
    assert "Bet placed!" in message.channel.sent[0]
