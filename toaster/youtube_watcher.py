"""Background YouTube watcher driven by config/youtube_watch.json."""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Optional
from xml.etree import ElementTree

import requests

from toaster.silent_times import is_silent_time


CONFIG_FILE = Path("config/youtube_watch.json")
SHORTS_CONFIG_FILE = Path("config/youtube_shorts_watch.json")
POLL_INTERVAL_SECONDS = 3600
POST_INTERVAL_SECONDS = 120
STATE_FILE = Path("config/youtube_watch_state.json")
SHORTS_STATE_FILE = Path("config/youtube_shorts_watch_state.json")
YOUTUBE_NS = "http://www.youtube.com/xml/schemas/2015"
ATOM_NS = "http://www.w3.org/2005/Atom"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _load_watch_config(config_file: Path = CONFIG_FILE) -> tuple[list[dict], int, int]:
    try:
        with config_file.open("r", encoding="utf-8") as watch_file:
            config = json.load(watch_file)
        if isinstance(config, list):
            return config, POLL_INTERVAL_SECONDS, POST_INTERVAL_SECONDS
        if not isinstance(config, dict):
            return [], POLL_INTERVAL_SECONDS, POST_INTERVAL_SECONDS
        watches = config.get("watches", [])
        return (
            watches if isinstance(watches, list) else [],
            int(config.get("poll_interval_seconds", POLL_INTERVAL_SECONDS)),
            int(config.get("post_interval_seconds", POST_INTERVAL_SECONDS)),
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return [], POLL_INTERVAL_SECONDS, POST_INTERVAL_SECONDS


def get_watch_list(config_file: Path = CONFIG_FILE) -> list[dict]:
    """Return configured YouTube watches."""
    return _load_watch_config(config_file)[0]


def _load_state(state_file_path: Path = STATE_FILE) -> Dict[str, object]:
    try:
        with state_file_path.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        return state if isinstance(state, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _get_video_state(state: Dict[str, object], state_key: str) -> tuple[Optional[str], set[str]]:
    value = state.get(state_key)
    if isinstance(value, dict):
        latest_id = value.get("latest_id")
        posted_ids = value.get("posted_ids", [])
        return latest_id, {str(video_id) for video_id in posted_ids if video_id}
    if isinstance(value, str):
        return value, set()
    return None, set()


def _save_video_state(
    state: Dict[str, object], state_key: str, latest_id: str, posted_ids: set[str],
    state_file_path: Path = STATE_FILE,
) -> None:
    state[state_key] = {
        "latest_id": latest_id,
        "posted_ids": list(posted_ids)[-1000:],
    }
    _save_state(state, state_file_path)


def get_stored_latest_videos() -> list[dict[str, str]]:
    """Return the latest video links currently persisted by the watcher."""
    state = _load_state()
    videos = []
    for entry in get_watch_list():
        if not isinstance(entry, dict) or not entry.get("enabled", True):
            continue
        handle = str(entry.get("username", "")).strip().lstrip("@")
        state_key = entry.get("name") or handle
        video_id, _ = _get_video_state(state, state_key)
        if not handle or not video_id:
            continue
        videos.append({
            "name": str(entry.get("name") or handle),
            "username": handle,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    return videos


async def check_latest_youtube(
    config_file: Path = CONFIG_FILE, include_shorts: bool = False
) -> tuple[int, int]:
    """Fetch each enabled YouTube watch and return successful and total counts."""
    watches = [
        entry for entry in get_watch_list(config_file)
        if isinstance(entry, dict)
        and entry.get("enabled", True)
        and entry.get("username")
    ]
    results = await asyncio.gather(*[
        asyncio.to_thread(
            get_latest_video, entry["username"].strip().lstrip("@"), 15, include_shorts
        )
        for entry in watches
    ], return_exceptions=True)
    successful = sum(isinstance(video, dict) and bool(video.get("id")) for video in results)
    return successful, len(watches)


def _save_state(state: Dict[str, object], state_file_path: Path = STATE_FILE) -> None:
    try:
        state_file_path.parent.mkdir(parents=True, exist_ok=True)
        with state_file_path.open("w", encoding="utf-8") as state_file:
            json.dump(state, state_file, indent=2)
    except OSError:
        pass


def _get_channel_id(handle: str, timeout: int = 15) -> Optional[str]:
    response = requests.get(
        f"https://www.youtube.com/@{handle}/videos",
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    match = re.search(
        r'"(?:channelId|externalId|browseId)":"(UC[a-zA-Z0-9_-]+)"',
        response.text,
    )
    return match.group(1) if match else None


def _get_short_video_ids(handle: str, timeout: int = 15) -> list[str]:
    response = requests.get(
        f"https://www.youtube.com/@{handle}/shorts",
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    return list(dict.fromkeys(re.findall(r"/shorts/([a-zA-Z0-9_-]{11})", response.text)))


def get_latest_video(
    handle: str, timeout: int = 15, include_shorts: bool = False
) -> Optional[Dict[str, str]]:
    """Return the latest video matching the requested Shorts mode."""
    channel_id = _get_channel_id(handle, timeout=timeout)
    if not channel_id:
        return None
    short_video_ids = _get_short_video_ids(handle, timeout=timeout)

    response = requests.get(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        headers=HEADERS,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        if not include_shorts or not short_video_ids:
            raise
        video_id = short_video_ids[0]
        return {
            "id": video_id,
            "title": "",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }
    root = ElementTree.fromstring(response.content)
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        video_id = entry.findtext(f"{{{YOUTUBE_NS}}}videoId")
        title = entry.findtext(f"{{{ATOM_NS}}}title")
        if not video_id:
            continue
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        if (video_id in short_video_ids) != include_shorts:
            continue
        return {"id": video_id, "title": title or "", "url": video_url}
    return None


def _matches_required_title_words(title: str, require_word: object) -> bool:
    """Return whether a title contains at least one configured required phrase."""
    if not require_word:
        return True
    words = require_word if isinstance(require_word, list) else [require_word]
    title_lower = title.casefold()
    return any(str(word).casefold() in title_lower for word in words if word)


async def _dispatch_videos(bot, pending_videos: asyncio.Queue, post_interval_seconds: int) -> None:
    """Post queued videos one at a time, spacing posts by two minutes."""
    next_post_at = 0.0
    event_loop = asyncio.get_running_loop()
    while True:
        entry, video, state_key, state, pending_ids, state_file_path = await pending_videos.get()
        pending_ids.discard((state_key, video["id"]))
        delay = next_post_at - event_loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            channel_id = int(entry["channel_id"])
            channel = bot.get_channel(channel_id)
            if channel is None:
                channel = await bot.fetch_channel(channel_id)
            latest_id, posted_ids = _get_video_state(state, state_key)
            if video["id"] in posted_ids or await _video_already_posted(channel, video["url"]):
                posted_ids.add(video["id"])
            else:
                slot = entry.get("silent_time")
                silent = is_silent_time(slot=slot) if slot is not None else False
                await channel.send(video["url"], silent=silent)
                posted_ids.add(video["id"])
            _save_video_state(
                state, state_key, latest_id or video["id"], posted_ids, state_file_path
            )
        except Exception:
            pass
        finally:
            pending_videos.task_done()
        next_post_at = event_loop.time() + post_interval_seconds


async def _video_already_posted(channel, video_url: str, lookback: int = 100) -> bool:
    """Return whether a video URL or ID appears in recent channel messages."""
    video_id = video_url.split("v=", 1)[-1]
    try:
        async for message in channel.history(limit=lookback):
            if video_url in message.content or video_id in message.content:
                return True
    except Exception:
        return False
    return False


async def _start_youtube_watcher(
    bot,
    config_file: Path,
    state_file_path: Path,
    include_shorts: bool,
) -> None:
    """Poll configured channels and queue newly discovered videos."""
    await bot.wait_until_ready()
    watches, poll_interval_seconds, post_interval_seconds = _load_watch_config(config_file)
    watches = [
        entry for entry in watches
        if isinstance(entry, dict)
        and entry.get("enabled", True)
        and entry.get("username")
        and entry.get("channel_id")
    ]
    if not watches:
        return

    state = _load_state(state_file_path)
    pending_videos = asyncio.Queue()
    pending_ids = set()
    asyncio.create_task(_dispatch_videos(bot, pending_videos, post_interval_seconds))

    while True:
        for entry in watches:
            try:
                handle = entry["username"].strip().lstrip("@")
                state_key = entry.get("name") or handle
                video = await asyncio.to_thread(get_latest_video, handle, 15, include_shorts)
                if not video:
                    continue
                if not _matches_required_title_words(video["title"], entry.get("require_word")):
                    continue
                latest_id, posted_ids = _get_video_state(state, state_key)
                _save_video_state(state, state_key, video["id"], posted_ids, state_file_path)
                pending_key = (state_key, video["id"])
                if video["id"] not in posted_ids and pending_key not in pending_ids:
                    pending_ids.add(pending_key)
                    await pending_videos.put(
                        (entry, video, state_key, state, pending_ids, state_file_path)
                    )
            except Exception:
                continue
        await asyncio.sleep(poll_interval_seconds)


async def start_youtube_watcher(bot) -> None:
    """Poll configured channels and queue newly discovered non-Short videos."""
    await _start_youtube_watcher(bot, CONFIG_FILE, STATE_FILE, include_shorts=False)


async def start_youtube_shorts_watcher(bot) -> None:
    """Poll configured channels and queue newly discovered Shorts."""
    await _start_youtube_watcher(bot, SHORTS_CONFIG_FILE, SHORTS_STATE_FILE, include_shorts=True)