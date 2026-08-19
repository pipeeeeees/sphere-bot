"""Background tweet watcher: polls configured X accounts and posts new tweets to channels.

Config: `config/twitter_watch.json` — list of {name, username, channel_id, enabled}
State persisted to: `config/twitter_watch_state.json` mapping username -> last_status_id
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict

from toaster.config import load_config
from toaster.modules.tweet_puller import get_latest_tweet_link, get_fixvx_equivalent
import requests


def _fixvx_has_video(url: str, timeout: int = 10) -> bool:
    """Best-effort check if the given fixvx/front-end URL embeds a video.

    Checks for <video> tags, common og:video meta tags, or player hints in HTML.
    """
    try:
        headers = {"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html = resp.text.lower()
        if "<video" in html:
            return True
        # OpenGraph video tags
        if "og:video" in html or "property=\"og:video\"" in html:
            return True
        # common player hints
        if "data-video-id" in html or "player" in html and "video" in html:
            return True
        return False
    except Exception:
        return False


def _fixvx_has_word(url: str, word: str, timeout: int = 10) -> bool:
    """Check if the provider page contains `word` in tweet text or meta tags."""
    if not word:
        return False
    try:
        headers = {"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html = resp.text.lower()
        w = word.lower()
        # Check meta description / og:description first
        if f"og:description" in html:
            # quick substring search
            if w in html:
                return True
        # Fallback: simple text search of page
        if w in html:
            return True
        return False
    except Exception:
        return False


CONFIG_FILE = Path("config") / "twitter_watch.json"
STATE_FILE = Path("config") / "twitter_watch_state.json"


def _load_watch_list():
    if not CONFIG_FILE.exists():
        return []
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _load_state() -> Dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict[str, str]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def _extract_status_id(link: str):
    if not link:
        return None
    m = re.search(r"/status(?:es)?/(\d+)", link)
    if m:
        return m.group(1)
    return None


async def start_tweet_watcher(bot, poll_interval_seconds: int = 300):
    """Run indefinitely, polling accounts and posting new tweets.

    - On first observation of an account (no stored state) do NOT post; just store.
    - When status id changes, post message to configured channel and update state.
    """
    await bot.wait_until_ready()
    watch_list = _load_watch_list()
    if not watch_list:
        return

    state = _load_state()

    while True:
        for entry in watch_list:
            try:
                if not entry.get("enabled", True):
                    continue
                username = entry.get("username")
                channel_id = int(entry.get("channel_id"))
                if not username:
                    continue

                link = get_latest_tweet_link(username)
                status_id = _extract_status_id(link) if link else None

                last_id = state.get(username)
                if last_id is None:
                    # First time seeing this account — record but don't post
                    if status_id:
                        state[username] = status_id
                        _save_state(state)
                    continue

                if status_id and status_id != last_id:
                    # New tweet — post to channel
                    try:
                        channel = bot.get_channel(channel_id)
                        if channel is None:
                            # try fetch
                            try:
                                channel = await bot.fetch_channel(channel_id)
                            except Exception:
                                channel = None
                        if channel is not None:
                            # Determine provider (per-entry override) and produce alternative link
                            provider = entry.get("provider", "fxtwitter")
                            alt = get_fixvx_equivalent(link, provider=provider) or link

                            # If this watch entry requires a video embed, verify before posting
                            require_video = bool(entry.get("require_video", False))
                            can_post = True
                            if require_video:
                                # run blocking check in thread
                                try:
                                    has_video = await asyncio.to_thread(_fixvx_has_video, alt)
                                except Exception:
                                    has_video = False
                                if not has_video:
                                    can_post = False

                            if can_post:
                                msg = f"New tweet from @{username}: {alt}"
                                await channel.send(msg)
                    except Exception:
                        # ignore failures and continue
                        pass

                    # update state
                    state[username] = status_id
                    _save_state(state)

            except Exception:
                continue

        await asyncio.sleep(poll_interval_seconds)
