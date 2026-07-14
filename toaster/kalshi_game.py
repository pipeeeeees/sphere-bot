import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_STARTING_BALANCE = 100000.0
STATE_FILE = Path("config/kalshi_game_state.json")


def _state_path() -> Path:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return STATE_FILE


def load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"users": {}}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"users": {}}


def save_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)


def _user_key(user_id: str) -> str:
    return f"user_{user_id}"


def _ensure_user(state: Dict[str, Any], user_id: str, display_name: str) -> Dict[str, Any]:
    key = _user_key(user_id)
    users = state.setdefault("users", {})
    if key not in users:
        users[key] = {
            "user_id": user_id,
            "display_name": display_name,
            "balance": DEFAULT_STARTING_BALANCE,
            "pending_bets": [],
            "bet_history": [],
            "transfers": [],
        }
    else:
        users[key]["display_name"] = display_name
    return users[key]


def parse_kalshi_bet_message(message: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"https://kalshi\.com/markets/[^\s]+", message)
    if not match:
        return None

    url = match.group(0)
    ticker = url.rstrip("/").split("/")[-1]
    amount_match = re.search(r"\$(\d+(?:\.\d+)?)", message)
    if not amount_match:
        return None

    outcome_match = re.search(r"(?:on|for)\s+([a-zA-Z0-9_\-]+)", message)
    if not outcome_match:
        return None

    return {
        "url": url,
        "ticker": ticker,
        "amount": float(amount_match.group(1)),
        "outcome": outcome_match.group(1).strip().lower(),
    }


def place_bet(state: Dict[str, Any], user_id: str, display_name: str, channel_id: int, url: str, amount: float, outcome: str) -> Dict[str, Any]:
    user = _ensure_user(state, user_id, display_name)
    if user["balance"] < 0:
        return {"ok": False, "reason": "You are already in negative balance and cannot place more bets."}
    if amount <= 0:
        return {"ok": False, "reason": "Bet amount must be positive."}
    if amount > user["balance"]:
        return {"ok": False, "reason": f"Bet amount exceeds your current balance of ${user['balance']:.2f}."}

    user["balance"] -= amount
    bet = {
        "id": f"bet-{len(user['pending_bets']) + 1}",
        "url": url,
        "ticker": url.rstrip("/").split("/")[-1],
        "amount": amount,
        "outcome": outcome.lower(),
        "channel_id": channel_id,
        "status": "pending",
    }
    user["pending_bets"].append(bet)
    user["bet_history"].append({
        "type": "bet",
        "amount": amount,
        "outcome": outcome.lower(),
        "ticker": bet["ticker"],
        "status": "pending",
        "url": url,
    })
    return {"ok": True, "bet": bet, "balance": user["balance"]}


def transfer_funds(state: Dict[str, Any], from_user_id: str, to_user_id: str, amount: float) -> Dict[str, Any]:
    from_user = _ensure_user(state, from_user_id, from_user_id)
    to_user = _ensure_user(state, to_user_id, to_user_id)
    if amount <= 0:
        return {"ok": False, "reason": "Transfer amount must be positive."}
    if from_user["balance"] < amount:
        return {"ok": False, "reason": "You do not have enough balance to transfer that amount."}

    from_user["balance"] -= amount
    to_user["balance"] += amount
    from_user["transfers"].append({"to": to_user_id, "amount": amount})
    from_user["bet_history"].append({"type": "transfer_out", "amount": amount, "to": to_user_id})
    to_user["bet_history"].append({"type": "transfer_in", "amount": amount, "from": from_user_id})
    return {"ok": True, "from_balance": from_user["balance"], "to_balance": to_user["balance"]}


def fetch_market_data(ticker: str) -> Dict[str, Any]:
    url = f"https://external-api.kalshi.com/trade-api/v2/markets/{ticker}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data.get("market") or {}


def _notify_resolution(bot: Any, user: Dict[str, Any], bet: Dict[str, Any], won: bool, balance: float) -> None:
    if bot is None:
        return

    async def _send() -> None:
        try:
            user_id_str = str(user["user_id"])
            recipient = None
            try:
                recipient = await bot.fetch_user(user_id_str)
            except TypeError:
                pass
            if recipient is None and user_id_str.isdigit():
                recipient = await bot.fetch_user(int(user_id_str))
            if recipient is None:
                return
            result_text = "won" if won else "lost"
            await recipient.send(
                f"🎲 Your Kalshi bet on {bet['ticker']} {result_text}! "
                f"You {'gained' if won else 'lost'} ${bet['amount']:.2f}. "
                f"Your new pretend balance is ${balance:.2f}."
            )
        except Exception as exc:
            print(f"Failed to notify Kalshi user {user['user_id']}: {exc}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_send())
    else:
        loop.create_task(_send())


def resolve_pending_bets(state: Dict[str, Any], bot=None) -> List[Dict[str, Any]]:
    resolved = []
    for user_key, user in list(state.get("users", {}).items()):
        pending = list(user.get("pending_bets", []))
        still_pending = []
        for bet in pending:
            try:
                market = fetch_market_data(bet["ticker"])
            except Exception:
                still_pending.append(bet)
                continue

            status = market.get("status") or ""
            if str(status).lower() != "resolved":
                still_pending.append(bet)
                continue

            result = str(market.get("result") or "").strip().lower()
            outcome = str(bet.get("outcome") or "").strip().lower()
            won = result == outcome
            payout = bet["amount"] if won else 0
            user["balance"] += payout
            bet["status"] = "resolved"
            bet["won"] = won
            bet["payout"] = payout
            user["bet_history"].append({
                "type": "bet_result",
                "ticker": bet["ticker"],
                "outcome": outcome,
                "won": won,
                "payout": payout,
            })
            _notify_resolution(bot, user, bet, won, user["balance"])
            resolved.append({"user_id": user["user_id"], "bet": bet, "won": won, "balance": user["balance"]})
        user["pending_bets"] = still_pending
    return resolved


async def monitor_pending_bets(bot: Any, interval_seconds: float = 60.0) -> None:
    while True:
        try:
            state = load_state()
            resolved = resolve_pending_bets(state, bot=bot)
            if resolved:
                save_state(state)
        except Exception as exc:
            print(f"Kalshi resolution loop error: {exc}")
        await asyncio.sleep(interval_seconds)


def format_balance(user: Dict[str, Any]) -> str:
    return f"${user['balance']:.2f}"


def format_history(user: Dict[str, Any]) -> str:
    if not user.get("bet_history"):
        return "No betting history yet."
    lines = ["Betting history:"]
    for item in user["bet_history"]:
        if item.get("type") == "bet":
            lines.append(f"- Bet {item['amount']:.2f} on {item['outcome']} for {item['ticker']} ({item['status']})")
        elif item.get("type") == "transfer_out":
            lines.append(f"- Sent ${item['amount']:.2f} to {item['to']}")
        elif item.get("type") == "transfer_in":
            lines.append(f"- Received ${item['amount']:.2f} from {item['from']}")
    return "\n".join(lines)
