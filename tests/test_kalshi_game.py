import json
from pathlib import Path

from toaster.kalshi_game import (
    DEFAULT_STARTING_BALANCE,
    parse_kalshi_bet_message,
    place_bet,
    transfer_funds,
    resolve_pending_bets,
)


class DummyBot:
    def __init__(self):
        self.sent = []

    async def fetch_user(self, user_id):
        return type("User", (), {"id": user_id, "send": self._send})()

    async def _send(self, message):
        self.sent.append(message)


def test_parse_kalshi_bet_message_extracts_amount_outcome_and_ticker(tmp_path):
    message = "https://kalshi.com/markets/kxwcadvance/world-cup-advance/kxwcadvance-26jul14fraesp $20 on france"
    parsed = parse_kalshi_bet_message(message)

    assert parsed is not None
    assert parsed["ticker"] == "kxwcadvance-26jul14fraesp"
    assert parsed["amount"] == 20.0
    assert parsed["outcome"] == "france"


def test_parse_kalshi_bet_message_handles_optional_article_before_outcome():
    message = "https://kalshi.com/markets/kxmlbgame/professional-baseball-game/kxmlbgame-26jul142000alnl give me $2000 on the AL"
    parsed = parse_kalshi_bet_message(message)

    assert parsed is not None
    assert parsed["outcome"] == "al"


def test_place_bet_and_transfer_update_balance(tmp_path):
    state = {"users": {}}
    user_a = place_bet(state, "u1", "Alice", 123, "https://kalshi.com/markets/x/y", 10.0, "france")
    assert user_a["ok"] is True
    assert state["users"]["user_u1"]["balance"] == DEFAULT_STARTING_BALANCE - 10.0

    user_b = place_bet(state, "u2", "Bob", 456, "https://kalshi.com/markets/x/y", 5.0, "argentina")
    assert user_b["ok"] is True

    transfer = transfer_funds(state, "u1", "u2", 15.0)
    assert transfer["ok"] is True
    assert state["users"]["user_u1"]["balance"] == DEFAULT_STARTING_BALANCE - 25.0
    assert state["users"]["user_u2"]["balance"] == DEFAULT_STARTING_BALANCE + 15.0 - 5.0


def test_resolve_pending_bet_updates_state_and_notifies(tmp_path, monkeypatch):
    state = {"users": {}}
    place_bet(state, "u1", "Alice", 123, "https://kalshi.com/markets/x/y", 10.0, "france")

    class FakeMarket:
        def __init__(self):
            self.data = {"status": "resolved", "result": "france"}

    monkeypatch.setattr("toaster.kalshi_game.fetch_market_data", lambda *args, **kwargs: FakeMarket().data)

    bot = DummyBot()
    resolved = resolve_pending_bets(state, bot=bot)

    assert resolved[0]["won"] is True
    assert state["users"]["user_u1"]["balance"] == DEFAULT_STARTING_BALANCE
    assert state["users"]["user_u1"]["pending_bets"] == []
    assert bot.sent
