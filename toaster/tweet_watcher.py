"""Background tweet watcher: polls configured X accounts and posts new tweets to channels.

Config: `config/twitter_watch.json` — {quiet_hours, watches}, where each watch has
{name, username, channel_id, enabled}
State persisted to: `config/twitter_watch_state.json` mapping username -> last_status_id
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, time
from typing import Dict, Optional

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
        # Strict checks: presence of an actual <video> tag or explicit video metadata
        if "<video" in html:
            return True
        # OpenGraph video tags (explicit)
        if "property=\"og:video\"" in html or "name=\"og:video\"" in html or "og:video" in html:
            return True
        # Twitter player meta
        if "name=\"twitter:player\"" in html or "twitter:player" in html:
            return True
        # JSON-LD VideoObject
        if '"@type":"videoobject"' in html or '"@type": "videoobject"' in html:
            return True
        # explicit video URL hints (mp4, m3u8) in the page
        if ".mp4" in html or ".m3u8" in html or "video_url" in html:
            return True

        # If none of the above explicit markers are present, treat as no video
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


def _extract_tweet_text(url: str, timeout: int = 10) -> Optional[str]:
    """Extract tweet text from a fixvx/frontend URL.
    
    Attempts to parse og:description meta tag or fallback to text content.
    """
    if not url:
        return None
    try:
        headers = {"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
        
        # Try to extract og:description (most reliable for tweet text)
        m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)
        if m:
            return m.group(1).strip()
        
        # Fallback: look for content attribute
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:description["\']', html)
        if m:
            return m.group(1).strip()
        
        return None
    except Exception:
        return None


def _is_college_football_related(tweet_text: str, timeout: int = 15) -> bool:
    """Use Gemini AI to classify if a tweet is college football related.
    
    Uses a two-layer approach:
    1. Quick keyword filter to reject obvious non-football content
    2. Gemini AI for nuanced cases
    
    Args:
        tweet_text: The tweet text to classify
        timeout: Request timeout in seconds
    
    Returns:
        True if Gemini determines it's college football related, False otherwise
    """
    if not tweet_text or not tweet_text.strip():
        return False
    
    text_lower = tweet_text.lower()
    
    # Layer 1: Quick keyword filters to reject obvious non-football sports
    # These are terms that indicate basketball, baseball, hockey, etc.
    non_football_keywords = [
        # Basketball
        "basketball", "nba", "nit", "ncaa tournament", "march madness", "hoops", "three-pointer", "dunk", "slam dunk",
        "jazz", "lakers", "celtics", "warriors", "nets", "76ers", "bucks", "heat", "mavericks", "nuggets",
        "suns", "grizzlies", "kings", "pelicans", "spurs", "raptors", "bulls", "cavaliers", "pistons", "pacers",
        "hawks", "hornets", "magic", "knicks", "rockets", "blazers", "clippers", "timberwolves",
        # Baseball
        "baseball", "mlb", "pitcher", "batter", "home run", "strikeout", "world series", "dugout",
        # Hockey
        "hockey", "nhl", "ice hockey", "puck", "goalie", "boarding", "hat trick", "zamboni",
        # Other sports
        "nfl pro", "professional football", "nba draft", "mlb draft", "nhl draft",
        "nfl game", "nfl team", "nfl player", "nfl draft",
        "soccer", "cricket", "rugby", "tennis", "golf", "boxing", "ufc", "mma",
    ]
    
    # Check if any non-football keyword appears in the tweet
    for keyword in non_football_keywords:
        if keyword in text_lower:
            return False
    
    # Layer 2: Use Gemini for final classification
    try:
        from toaster.llm_agents.gemini import get_gemini_response_with_key
        
        # Create a very explicit prompt for college football classification
        classification_prompt = f"""You are a college sports expert. Determine if the following tweet is EXCLUSIVELY about COLLEGE FOOTBALL.

COLLEGE FOOTBALL ONLY includes:
- NCAA Division I FBS (Football Bowl Subdivision) and FCS (Football Championship Subdivision) football
- College football recruiting (players committing to college football programs)
- College football transfer portal and portal updates
- College football games, scores, and results
- Bowl games (January bowl season, etc.)
- College football playoffs (College Football Playoff)
- College football coaches, teams, conferences
- College football strategy and analysis

EXPLICITLY EXCLUDE (return "no" for these):
- NBA (basketball), NCAA basketball, March Madness - any basketball at any level
- MLB (baseball), minor league baseball, college baseball
- Hockey (NHL, college hockey, any level)
- NFL (professional football) or NFL draft
- Soccer, cricket, rugby, tennis, golf, boxing, MMA, UFC
- Any sport OTHER than college football

Tweet: "{tweet_text}"

You must respond with ONLY "yes" or "no" (lowercase, no other text).
If the tweet mentions basketball, baseball, hockey, or any non-football sport, respond "no".
If unsure, respond "no" (be conservative)."""
        
        response, error = get_gemini_response_with_key(
            history="",
            message=classification_prompt,
            config_path="config"
        )
        
        if error or not response:
            # On error, default to False (don't post) to avoid false positives
            return False
        
        # Check if response starts with "yes"
        return response.strip().lower().startswith("yes")
    
    except Exception:
        # If Gemini is not available or errors occur, default to False
        return False


CONFIG_FILE = Path("config") / "twitter_watch.json"
STATE_FILE = Path("config") / "twitter_watch_state.json"
DEFAULT_WEEKDAY_QUIET_START = time(0, 0)
DEFAULT_WEEKDAY_QUIET_END = time(6, 0)


def _load_watch_config():
    if not CONFIG_FILE.exists():
        return {}, []
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = json.load(f)
        if isinstance(config, list):
            return {}, config
        if isinstance(config, dict):
            watches = config.get("watches", [])
            quiet_hours = config.get("quiet_hours", {})
            if not isinstance(quiet_hours, dict):
                quiet_hours = {}
            return quiet_hours, watches if isinstance(watches, list) else []
    except Exception:
        pass
    return {}, []


def _parse_config_time(value, default: time) -> time:
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def is_tweet_watch_quiet_hours(now: Optional[datetime] = None) -> bool:
    """Return whether weekday tweet posting is currently suppressed."""
    current_time = now or datetime.now()
    if current_time.weekday() >= 5:
        return False
    quiet_hours, _ = _load_watch_config()
    quiet_start = _parse_config_time(quiet_hours.get("weekday_start"), DEFAULT_WEEKDAY_QUIET_START)
    quiet_end = _parse_config_time(quiet_hours.get("weekday_end"), DEFAULT_WEEKDAY_QUIET_END)
    if quiet_start <= quiet_end:
        return quiet_start <= current_time.time() < quiet_end
    return current_time.time() >= quiet_start or current_time.time() < quiet_end


def _load_watch_list():
    _, watches = _load_watch_config()
    return watches


def get_watch_list():
    """Public accessor for the configured watch list."""
    return _load_watch_list()


def _load_state() -> Dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_saved_state() -> Dict[str, str]:
    """Public accessor for persisted watch state."""
    return _load_state()


async def check_latest_tweets():
    """Fetch the latest tweet for each enabled watch and return success counts."""
    watch_list = _load_watch_list()
    enabled_entries = [
        entry for entry in watch_list
        if entry.get("enabled", True) and entry.get("username")
    ]

    results = await asyncio.gather(*[
        asyncio.to_thread(get_latest_tweet_link, entry["username"])
        for entry in enabled_entries
    ], return_exceptions=True)
    successful = sum(
        isinstance(link, str) and bool(_extract_status_id(link))
        for link in results
    )
    return successful, len(enabled_entries)


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


async def _tweet_already_posted(channel, tweet_url: str, lookback: int = 10) -> bool:
    """Check if the tweet URL has already been posted in the channel's recent history.
    
    Args:
        channel: Discord channel object
        tweet_url: The tweet URL to check for
        lookback: Number of recent messages to check (default 10)
    
    Returns:
        True if the tweet URL is found in recent messages, False otherwise
    """
    if not channel or not tweet_url:
        return False
    
    try:
        # Fetch recent messages from the channel
        async for message in channel.history(limit=lookback):
            # Check if this message contains the tweet URL (or a normalized version)
            if tweet_url in message.content:
                return True
            # Also check for x.com version if we have a fixvx link
            if "x.com" in tweet_url or "twitter.com" in tweet_url:
                # Extract status ID and check for it in any URL format
                status_id = _extract_status_id(tweet_url)
                if status_id and f"/status/{status_id}" in message.content:
                    return True
    except Exception:
        # If we can't fetch history, assume it's safe to post
        pass
    
    return False


async def start_tweet_watcher(bot, poll_interval_seconds: int = 300):
    """Run indefinitely, polling accounts and posting new tweets.

    - On first observation of an account (no stored state) do NOT post; just store.
    - When status id changes, post message to configured channel and update state.
    - Before posting, check recent channel history to avoid duplicate posts.
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
                    if is_tweet_watch_quiet_hours():
                        continue

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

                            # Check if this tweet has already been posted in recent history
                            already_posted = await _tweet_already_posted(channel, alt, lookback=10)
                            if already_posted:
                                # Skip posting, but still update state so we don't check again
                                state[username] = status_id
                                _save_state(state)
                                continue

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

                            # If this watch entry requires a specific word, verify before posting
                            require_word = entry.get("require_word")
                            if require_word and can_post:
                                # support list or single string
                                try:
                                    if isinstance(require_word, list):
                                        found = False
                                        for w in require_word:
                                            try:
                                                ok = await asyncio.to_thread(_fixvx_has_word, alt, w)
                                            except Exception:
                                                ok = False
                                            if ok:
                                                found = True
                                                break
                                        if not found:
                                            can_post = False
                                    else:
                                        try:
                                            ok = await asyncio.to_thread(_fixvx_has_word, alt, require_word)
                                        except Exception:
                                            ok = False
                                        if not ok:
                                            can_post = False
                                except Exception:
                                    can_post = False

                            # If this watch entry requires AI classification, verify before posting
                            require_ai_classification = entry.get("require_ai_classification")
                            if require_ai_classification and can_post:
                                # Extract tweet text and run AI classification in thread
                                try:
                                    tweet_text = await asyncio.to_thread(_extract_tweet_text, alt)
                                    if tweet_text:
                                        classification_ok = await asyncio.to_thread(_is_college_football_related, tweet_text)
                                        if not classification_ok:
                                            can_post = False
                                    else:
                                        # If we can't extract text, don't post to be safe
                                        can_post = False
                                except Exception:
                                    can_post = False

                            if can_post:
                                await channel.send(alt)
                    except Exception:
                        # ignore failures and continue
                        pass

                    # update state
                    state[username] = status_id
                    _save_state(state)

            except Exception:
                continue

        await asyncio.sleep(poll_interval_seconds)
