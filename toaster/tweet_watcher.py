"""Background tweet watcher: polls configured X accounts and posts new tweets to channels.

Config: `config/twitter_watch.json` — {quiet_hours, watches}, where each watch has
{name, username, channel_id, enabled}
State persisted to: `config/twitter_watch_state.json` mapping username -> last_status_id
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, time, timezone
from statistics import NormalDist
from typing import Dict, Optional

from toaster.config import load_config
from toaster.modules.tweet_puller import get_latest_tweet_links, get_fixvx_equivalent
from toaster.silent_times import is_silent_time
import requests


# This channel intentionally receives both filter feedback and runtime errors so
# future Copilot sessions can diagnose the watcher from one Discord history.
FEEDBACK_CHANNEL_ID = 1539108566009643048


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


def _coerce_metric_to_int(value: object) -> Optional[int]:
    """Normalize a metric value like 1.2M, 320K, or 12345 into an integer."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMB])?", text, flags=re.IGNORECASE)
    if not match:
        try:
            return int(float(text))
        except ValueError:
            return None
    number = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    multiplier = {"K": 1000, "M": 1000000, "B": 1000000000}.get(suffix, 1)
    return int(number * multiplier)


def _get_fxtwitter_view_count(url: str, timeout: int = 10) -> Optional[int]:
    """Return the view count for a tweet from the fxtwitter status API."""
    status_id = _extract_status_id(url)
    if not status_id:
        return None
    try:
        response = requests.get(
            f"https://api.fxtwitter.com/status/{status_id}",
            headers={"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json() if isinstance(response.json(), dict) else {}
        tweet = payload.get("tweet") if isinstance(payload.get("tweet"), dict) else {}
        views = tweet.get("views")
        if views is None:
            views = payload.get("views")
        return _coerce_metric_to_int(views)
    except (TypeError, ValueError, requests.RequestException, AttributeError):
        return None


def _get_fxtwitter_created_at(url: str, timeout: int = 10) -> Optional[datetime]:
    """Return the tweet creation time from the fxtwitter status API."""
    status_id = _extract_status_id(url)
    if not status_id:
        return None
    try:
        response = requests.get(
            f"https://api.fxtwitter.com/status/{status_id}",
            headers={"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json() if isinstance(response.json(), dict) else {}
        tweet = payload.get("tweet") if isinstance(payload.get("tweet"), dict) else {}
        created_at = tweet.get("created_at") or payload.get("created_at") or tweet.get("created_at_epoch")
        if created_at is None:
            return None
        if isinstance(created_at, (int, float)):
            dt = datetime.fromtimestamp(float(created_at), tz=timezone.utc)
            return dt
        if isinstance(created_at, datetime):
            return created_at.astimezone(timezone.utc)
        parsed = str(created_at).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(parsed)
        except ValueError:
            try:
                dt = datetime.strptime(parsed, "%Y-%m-%d %H:%M:%S%z")
            except ValueError:
                try:
                    dt = datetime.strptime(parsed, "%a %b %d %H:%M:%S %z %Y")
                except ValueError:
                    return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, requests.RequestException, AttributeError):
        return None


def _calculate_views_per_minute(url: str, timeout: int = 10) -> Optional[float]:
    """Calculate views divided by minutes since the tweet first appeared."""
    view_count = _get_fxtwitter_view_count(url, timeout=timeout)
    created_at = _get_fxtwitter_created_at(url, timeout=timeout)
    if view_count is None or created_at is None:
        return None
    age_minutes = (datetime.now(timezone.utc) - created_at).total_seconds() / 60.0
    if age_minutes <= 0:
        age_minutes = 1.0
    return view_count / age_minutes


def _fxtwitter_has_media_type(url: str, media_type: str, timeout: int = 10) -> bool:
    """Return whether the tweet has media of the requested fxtwitter type."""
    status_id = _extract_status_id(url)
    if not status_id:
        return False
    try:
        response = requests.get(
            f"https://api.fxtwitter.com/status/{status_id}",
            headers={"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"},
            timeout=timeout,
        )
        response.raise_for_status()
        media = response.json().get("tweet", {}).get("media", {}).get("all", [])
        return any(item.get("type") == media_type for item in media if isinstance(item, dict))
    except (TypeError, ValueError, requests.RequestException, AttributeError):
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
        status_id = _extract_status_id(url)
        if status_id:
            try:
                api_response = requests.get(
                    f"https://api.fxtwitter.com/status/{status_id}",
                    headers={"User-Agent": "news-headlines-fetcher/1.0 (+https://example.com)"},
                    timeout=timeout,
                )
                api_response.raise_for_status()
                tweet = api_response.json().get("tweet", {})
                api_text = tweet.get("text")
                if api_text:
                    return api_text.strip()
            except Exception:
                pass

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

    def contains_keyword(value: str, keyword: str) -> bool:
        if not keyword:
            return False
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", value) is not None

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
        if contains_keyword(text_lower, keyword):
            return False

    # Layer 2: Accept obvious college-football context before the AI fallback.
    # Some real CFB posts are framed as quotes or game recaps without the exact
    # phrase "college football" in them, and the Gemini step is intentionally
    # conservative when it is unsure.
    obvious_college_football_signals = [
        "college football", "ncaa football", "cfb", "fbs", "fcs", "hail mary",
        "touchdown", "quarterback", "qb", "offense", "defense", "field stormed",
        "stormed the field", "bowl game", "college football playoff", "transfer portal",
        "recruiting", "big ten", "sec", "acc", "big 12", "pac-12", "game day",
        "coach", "head coach", "offensive coordinator", "defensive coordinator",
        "running back", "wide receiver", "linebacker", "safety", "playoff",
        "conference title", "job security", "team needs", "commitment", "player development",
        "espn fpi", "fpi", "week 1", "week one", "updated espn fpi", "college football season"
    ]
    if any(contains_keyword(text_lower, signal) for signal in obvious_college_football_signals):
        return True

    football_programs = [
        "alabama", "arkansas", "auburn", "clemson", "florida", "florida state",
        "georgia", "kansas", "lsu", "michigan", "miami", "nc state", "notre dame",
        "ohio state", "oklahoma", "oregon", "penn state", "scarlet knights", "smu",
        "texas", "tennessee", "usc", "utah", "washington", "wisconsin"
    ]
    football_roles = [
        "qb", "quarterback", "recruit", "recruiting", "head coach", "assistant coach",
        "offensive coordinator", "defensive coordinator", "playmaker", "portal",
        "job security", "commitment", "signed", "depth chart"
    ]
    if any(contains_keyword(text_lower, program) for program in football_programs) and any(contains_keyword(text_lower, role) for role in football_roles):
        return True

    # Layer 3: Use Gemini for final classification
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = REPOSITORY_ROOT / "config" / "twitter_watch.json"
STATE_FILE = REPOSITORY_ROOT / "config" / "twitter_watch_state.json"
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


def _load_state() -> Dict[str, object]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_saved_state() -> Dict[str, object]:
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
        asyncio.to_thread(get_latest_tweet_links, entry["username"], 5)
        for entry in enabled_entries
    ], return_exceptions=True)
    successful = sum(
        isinstance(links, list) and any(_extract_status_id(link) for link in links)
        for links in results
    )
    return successful, len(enabled_entries)


def _save_state(state: Dict[str, object]) -> bool:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return True
    except Exception:
        return False


def _vpm_state_key(state_key: str) -> str:
    return f"{state_key}:vpm"


def _load_vpm_state(
    state: Dict[str, object], state_key: str
) -> tuple[Optional[float], int, float]:
    raw = state.get(_vpm_state_key(state_key))
    if not isinstance(raw, dict):
        return None, 0, 0.0
    try:
        mean = float(raw.get("mean")) if raw.get("mean") is not None else None
        count = int(raw.get("count", 0)) if raw.get("count") is not None else 0
        m2 = float(raw.get("m2", 0.0)) if raw.get("m2") is not None else 0.0
    except (TypeError, ValueError):
        return None, 0, 0.0
    return mean, max(0, count), max(0.0, m2)


async def _save_vpm_state(
    bot, state: Dict[str, object], state_key: str, mean: float, count: int, m2: float
) -> None:
    try:
        state[_vpm_state_key(state_key)] = {
            "mean": float(mean),
            "count": int(count),
            "m2": float(m2),
        }
        if not _save_state(state):
            raise OSError(f"Could not write VPM state to {STATE_FILE}")
    except Exception as exc:
        await _send_vpm_error(bot, f"Error storing rolling VPM average for {state_key}: {exc}")
        raise


async def _send_vpm_error(bot, detail: str) -> None:
    """Post VPM calculation or state errors to the feedback channel."""
    try:
        feedback_channel = bot.get_channel(FEEDBACK_CHANNEL_ID)
        if feedback_channel is None:
            feedback_channel = await bot.fetch_channel(FEEDBACK_CHANNEL_ID)
        if feedback_channel:
            await feedback_channel.send(f"⚠️ **VPM Error**\n**Details:** {detail}")
    except Exception:
        pass


def _vpm_percentile(value: object) -> Optional[float]:
    """Return a valid inclusive VPM percentile, rejecting legacy booleans."""
    if isinstance(value, bool):
        return None
    try:
        percentile = float(value)
    except (TypeError, ValueError):
        return None
    return percentile if 0.0 <= percentile <= 1.0 else None


def _vpm_threshold(percentile: float, mean: float, count: int, m2: float) -> float:
    """Estimate the VPM cutoff at a percentile using a normal distribution."""
    if percentile <= 0.0:
        return float("-inf")
    if percentile >= 1.0:
        return float("inf")
    variance = m2 / (count - 1) if count > 1 else 0.0
    standard_deviation = variance ** 0.5
    return mean + NormalDist().inv_cdf(percentile) * standard_deviation


def get_vpm_threshold_report() -> str:
    """Return current VPM counts, averages, and posting thresholds by watch."""
    state = _load_state()
    lines = ["📊 **VPM Thresholds**", "Counted values are successfully calculated VPMs per watch."]
    report_entries = [entry for entry in _load_watch_list() if entry.get("enabled", True)]
    if not report_entries:
        return "📊 **VPM Thresholds**\nNo enabled tweet watches configured."

    for entry in report_entries:
        state_key = str(entry.get("name") or entry.get("username") or "tweet_watch")
        mean, count, m2 = _load_vpm_state(state, state_key)
        percentile = _vpm_percentile(entry.get("post_if_better_than_average"))
        if mean is None or count <= 0:
            average_text = "N/A"
            threshold_text = "N/A"
        else:
            average_text = f"{mean:.2f}"
            if percentile is None:
                threshold_text = "N/A (not configured)"
            else:
                threshold_text = f"{_vpm_threshold(percentile, mean, count, m2):.2f}"

        channel_id = entry.get("channel_id", "unknown")
        watch_name = entry.get("name") or entry.get("username") or "unnamed watch"
        percentile_text = f"{percentile:.2f}" if percentile is not None else "N/A"
        lines.append(
            f"\n**{watch_name}** | Channel `{channel_id}`\n"
            f"Tweets counted: **{count}**\n"
            f"Rolling average VPM: **{average_text}**\n"
            f"Posting threshold ({percentile_text} percentile): **{threshold_text}**"
        )
    return "\n".join(lines)


def _update_vpm_stats(mean: float, count: int, m2: float, value: float) -> tuple[float, int, float]:
    """Add one VPM value using Welford's numerically stable update."""
    new_count = count + 1
    delta = value - mean
    new_mean = mean + (delta / new_count)
    new_m2 = m2 + (delta * (value - new_mean))
    return new_mean, new_count, max(0.0, new_m2)


def _get_seen_status_ids(state: Dict[str, object], state_key: str) -> set[str]:
    """Read seen IDs, including the legacy single-ID state format."""
    value = state.get(state_key)
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(status_id) for status_id in value}
    return set()


def _record_seen_status_id(
    state: Dict[str, object], state_key: str, seen_ids: set[str], status_id: str
) -> None:
    """Record a status ID while bounding persisted history."""
    seen_ids.add(status_id)
    state[state_key] = list(seen_ids)[-1000:]
    _save_state(state)


def _extract_status_id(link: str):
    if not link:
        return None
    m = re.search(r"/status(?:es)?/(\d+)", link)
    if m:
        return m.group(1)
    return None


async def _tweet_already_posted(
    channel,
    tweet_url: str,
    lookback: int = 10,
    bot=None,
    entry: Optional[Dict[str, object]] = None,
) -> bool:
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
    except Exception as exc:
        if bot is not None:
            await _send_error_feedback(bot, "checking recent channel history", exc, entry, tweet_url)
        # If we can't fetch history, assume it's safe to post
        pass
    
    return False


async def _send_filter_feedback(bot, tweet_url: str, reason: str) -> None:
    """Send feedback about a filtered tweet to the feedback channel.
    
    Args:
        bot: Discord bot instance
        tweet_url: The URL of the tweet that was filtered
        reason: The reason why the tweet was filtered
    """
    await _send_feedback_message(
        bot,
        f"🚫 **Filtered Tweet**\n**Reason:** {reason}\n**URL:** {tweet_url}",
    )


async def _send_feedback_message(bot, content: str) -> None:
    """Send watcher feedback or diagnostics to the dedicated feedback channel."""
    try:
        feedback_channel = bot.get_channel(FEEDBACK_CHANNEL_ID)
        if feedback_channel is None:
            feedback_channel = await bot.fetch_channel(FEEDBACK_CHANNEL_ID)

        if feedback_channel:
            await feedback_channel.send(content)
    except Exception:
        # Reporting must never raise another error or interrupt tweet processing.
        pass


async def _send_error_feedback(
    bot,
    operation: str,
    detail: object,
    entry: Optional[Dict[str, object]] = None,
    tweet_url: Optional[str] = None,
) -> None:
    """Post actionable watcher errors with enough context for diagnosis."""
    watch_name = (entry or {}).get("name") or (entry or {}).get("username") or "unknown watch"
    error_type = type(detail).__name__
    message = (
        f"⚠️ **Tweet Watcher Error**\n"
        f"**Operation:** {operation}\n"
        f"**Watch:** {watch_name}\n"
        f"**Error:** `{error_type}: {detail}`"
    )
    if tweet_url:
        message += f"\n**URL:** {tweet_url}"
    await _send_feedback_message(bot, message)


async def _post_tweet(bot, entry: Dict[str, object], link: str) -> None:
    """Post one queued tweet, applying the watch entry's filters."""
    provider = entry.get("provider", "fxtwitter")
    alt = get_fixvx_equivalent(link, provider=provider) or link
    state = _load_state()
    state_key = str(entry.get("name") or entry.get("username") or "tweet_watch")
    can_post = True
    filter_reason = None
    vpm_report = None

    vpm_percentile = _vpm_percentile(entry.get("post_if_better_than_average"))
    if entry.get("post_if_better_than_average") is not None and vpm_percentile is None:
        can_post = False
        filter_reason = "Invalid VPM percentile; expected a number from 0.0 to 1.0"
    try:
        tweet_vpm = await asyncio.to_thread(_calculate_views_per_minute, alt)
        if tweet_vpm is None:
            raise ValueError("VPM calculation returned no result")
        rolling_mean, rolling_count, rolling_m2 = _load_vpm_state(state, state_key)
        threshold = None
        threshold_label = (
            f"{vpm_percentile:.2f} percentile threshold"
            if vpm_percentile is not None
            else "Posting threshold"
        )
        if rolling_mean is None or rolling_count <= 0:
            new_mean, new_count, new_m2 = tweet_vpm, 1, 0.0
            vpm_report = (
                f"**Tweet VPM:** {tweet_vpm:.2f}\n"
                f"**{threshold_label}:** N/A (initial sample)\n"
                f"**Rolling average:** N/A (initial sample)"
            )
        else:
            threshold = (
                _vpm_threshold(vpm_percentile, rolling_mean, rolling_count, rolling_m2)
                if vpm_percentile is not None
                else None
            )
            threshold_text = f"{threshold:.2f}" if threshold is not None else "N/A (not configured)"
            vpm_report = (
                f"**Tweet VPM:** {tweet_vpm:.2f}\n"
                f"**{threshold_label}:** {threshold_text}\n"
                f"**Rolling average:** {rolling_mean:.2f}"
            )
            if threshold is not None and tweet_vpm <= threshold:
                can_post = False
                filter_reason = (
                    f"Less than popular VPM (tweet VPM: {tweet_vpm:.2f}, "
                    f"{vpm_percentile:.2f} percentile threshold: {threshold:.2f}, "
                    f"rolling average: {rolling_mean:.2f})"
                )
            new_mean, new_count, new_m2 = _update_vpm_stats(
                rolling_mean, rolling_count, rolling_m2, tweet_vpm
            )
        await _save_vpm_state(bot, state, state_key, new_mean, new_count, new_m2)
    except Exception as exc:
        await _send_vpm_error(bot, f"Error calculating or updating VPM for {state_key}: {exc}")
        can_post = False
        filter_reason = "Error calculating VPM for rolling average"

    if is_tweet_watch_quiet_hours():
        await _send_filter_feedback(bot, alt, "Quiet hours active")
        return

    channel_id = int(entry.get("channel_id"))
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as exc:
            await _send_error_feedback(bot, "fetching destination channel", exc, entry, link)
            channel = None
    if channel is None:
        await _send_error_feedback(
            bot,
            "finding destination channel",
            f"Channel {channel_id} was not found",
            entry,
            link,
        )
        return

    if await _tweet_already_posted(channel, alt, lookback=10, bot=bot, entry=entry):
        await _send_filter_feedback(bot, alt, "Already posted in channel")
        return

    if entry.get("require_video") and can_post:
        try:
            can_post = await asyncio.to_thread(_fixvx_has_video, alt)
        except Exception as exc:
            await _send_error_feedback(bot, "checking required video", exc, entry, alt)
            can_post = False
            filter_reason = "Error checking required video"
        if not can_post:
            filter_reason = "Missing required video"

    if entry.get("require_photo") and can_post:
        has_photo = await asyncio.to_thread(_fxtwitter_has_media_type, alt, "photo")
        if not has_photo:
            can_post = False
            filter_reason = "Missing required photo"

    if entry.get("require_photo_or_video") and can_post:
        try:
            has_photo = await asyncio.to_thread(_fxtwitter_has_media_type, alt, "photo")
            has_video = await asyncio.to_thread(_fixvx_has_video, alt)
            if not has_photo and not has_video:
                can_post = False
                filter_reason = "Missing required photo or video"
        except Exception as exc:
            await _send_error_feedback(bot, "checking required photo or video", exc, entry, alt)
            can_post = False
            filter_reason = "Error checking required photo or video"

    min_views = entry.get("min_views")
    if min_views is not None and can_post:
        try:
            view_count = await asyncio.to_thread(_get_fxtwitter_view_count, alt)
            if view_count is None or view_count < int(min_views):
                can_post = False
                filter_reason = (
                    f"Insufficient views (got {view_count or 0}, need {min_views}) "
                    f"| VPM: {await asyncio.to_thread(_calculate_views_per_minute, alt) or 0:.2f}"
                )
        except (TypeError, ValueError) as exc:
            await _send_error_feedback(bot, "checking minimum views", exc, entry, alt)
            can_post = False
            filter_reason = "Error checking view count"

    require_word = entry.get("require_word")
    if require_word and can_post:
        try:
            words = require_word if isinstance(require_word, list) else [require_word]
            found = False
            for word in words:
                try:
                    if await asyncio.to_thread(_fixvx_has_word, alt, word):
                        found = True
                        break
                except Exception as exc:
                    await _send_error_feedback(bot, "checking required word", exc, entry, alt)
                    continue
            if not found:
                can_post = False
                filter_reason = f"Missing required words: {', '.join(words)}"
        except Exception as exc:
            await _send_error_feedback(bot, "checking required words", exc, entry, alt)
            can_post = False
            filter_reason = "Error checking for required words"

    require_ai_classification = entry.get("require_ai_classification")
    if require_ai_classification and can_post:
        try:
            tweet_text = await asyncio.to_thread(_extract_tweet_text, alt)
            if tweet_text:
                can_post = await asyncio.to_thread(_is_college_football_related, tweet_text)
                if not can_post:
                    filter_reason = "Not classified as college football related"
            else:
                can_post = False
                filter_reason = "Could not extract tweet text"
        except Exception as exc:
            await _send_error_feedback(bot, "classifying tweet with AI", exc, entry, alt)
            can_post = False
            filter_reason = "Error during AI classification"

    if can_post:
        slot = entry.get("silent_time")
        silent = is_silent_time(slot=slot) if slot is not None else False
        await channel.send(alt, silent=silent)
        if vpm_report:
            await _send_feedback_message(
                bot,
                f"📈 **Posted Tweet VPM Stats**\n{vpm_report}\n**URL:** {alt}",
            )
    elif filter_reason:
        await _send_filter_feedback(bot, alt, filter_reason)


async def _dispatch_tweets(bot, pending_tweets: asyncio.Queue) -> None:
    """Drain queued tweets one at a time, spacing posts by two minutes."""
    next_post_at = 0.0
    event_loop = asyncio.get_running_loop()
    while True:
        entry, link = await pending_tweets.get()
        delay = next_post_at - event_loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            await _post_tweet(bot, entry, link)
        except Exception as exc:
            await _send_error_feedback(bot, "dispatching queued tweet", exc, entry, link)
        finally:
            pending_tweets.task_done()
        next_post_at = event_loop.time() + 120


async def start_tweet_watcher(bot, poll_interval_seconds: int = 300):
    """Run indefinitely, polling accounts and posting new tweets.

    - On first observation of an account (no stored state) do NOT post; just store.
    - When an unseen status appears in the latest five, queue it and update state.
    - Queued tweets are posted one at a time, with two minutes between posts.
    - Before posting, check recent channel history to avoid duplicate posts.
    - Send feedback for filtered tweets to the feedback channel.
    """
    await bot.wait_until_ready()
    watch_list = _load_watch_list()
    if not watch_list:
        return

    state = _load_state()
    pending_tweets = asyncio.Queue()
    asyncio.create_task(_dispatch_tweets(bot, pending_tweets))
    username_counts = {}
    for entry in watch_list:
        username = entry.get("username")
        if username:
            username_counts[username] = username_counts.get(username, 0) + 1

    while True:
        for entry in watch_list:
            try:
                if not entry.get("enabled", True):
                    continue
                username = entry.get("username")
                channel_id = int(entry.get("channel_id"))
                if not username:
                    continue
                state_key = username
                if username_counts.get(username, 0) > 1:
                    state_key = entry.get("name") or username

                links = await asyncio.to_thread(get_latest_tweet_links, username, 5)
                seen_ids = _get_seen_status_ids(state, state_key)
                if state_key not in state:
                    # First time seeing an account — establish a baseline without posting.
                    current_ids = {
                        status_id for status_id in (_extract_status_id(link) for link in links)
                        if status_id
                    }
                    if current_ids:
                        state[state_key] = list(current_ids)
                        _save_state(state)
                    continue

                for link in links:
                    status_id = _extract_status_id(link)
                    if not status_id or status_id in seen_ids:
                        continue

                    await pending_tweets.put((entry, link))

                    _record_seen_status_id(state, state_key, seen_ids, status_id)

            except Exception as exc:
                await _send_error_feedback(bot, "polling tweet watch", exc, entry)
                continue

        await asyncio.sleep(poll_interval_seconds)
