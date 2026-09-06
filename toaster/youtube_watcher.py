"""Background YouTube watcher driven by config/youtube_watch.json."""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Optional
from xml.etree import ElementTree

import requests

from toaster.silent_times import format_silent_post


CONFIG_FILE = Path("config/youtube_watch.json")
POLL_INTERVAL_SECONDS = 3600
POST_INTERVAL_SECONDS = 120
STATE_FILE = Path("config/youtube_watch_state.json")
YOUTUBE_NS = "http://www.youtube.com/xml/schemas/2015"
ATOM_NS = "http://www.w3.org/2005/Atom"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _load_watch_config() -> tuple[list[dict], int, int]:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
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


def get_watch_list() -> list[dict]:
    """Return configured YouTube watches."""
    return _load_watch_config()[0]


def _load_state() -> Dict[str, object]:
    try:
        with STATE_FILE.open("r", encoding="utf-8") as state_file:
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
    state: Dict[str, object], state_key: str, latest_id: str, posted_ids: set[str]
) -> None:
    state[state_key] = {
        "latest_id": latest_id,
        "posted_ids": list(posted_ids)[-1000:],
    }
    _save_state(state)


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


async def check_latest_youtube() -> tuple[int, int]:
    """Fetch each enabled YouTube watch and return successful and total counts."""
    watches = [
        entry for entry in get_watch_list()
        if isinstance(entry, dict)
        and entry.get("enabled", True)
        and entry.get("username")
    ]
    results = await asyncio.gather(*[
        asyncio.to_thread(get_latest_video, entry["username"].strip().lstrip("@"))
        for entry in watches
    ], return_exceptions=True)
    successful = sum(isinstance(video, dict) and bool(video.get("id")) for video in results)
    return successful, len(watches)


def _save_state(state: Dict[str, str]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as state_file:
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


def _get_short_video_ids(handle: str, timeout: int = 15) -> set[str]:
    response = requests.get(
        f"https://www.youtube.com/@{handle}/shorts",
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    return set(re.findall(r"/shorts/([a-zA-Z0-9_-]{11})", response.text))


def get_latest_video(handle: str, timeout: int = 15) -> Optional[Dict[str, str]]:
    """Return the latest non-Short video from a YouTube channel."""
    channel_id = _get_channel_id(handle, timeout=timeout)
    if not channel_id:
        return None
    short_video_ids = _get_short_video_ids(handle, timeout=timeout)

    response = requests.get(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        video_id = entry.findtext(f"{{{YOUTUBE_NS}}}videoId")
        title = entry.findtext(f"{{{ATOM_NS}}}title")
        if not video_id:
            continue
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        if video_id in short_video_ids:
            continue
        return {"id": video_id, "title": title or "", "url": video_url}
    return None


async def _dispatch_videos(bot, pending_videos: asyncio.Queue, post_interval_seconds: int) -> None:
    """Post queued videos one at a time, spacing posts by two minutes."""
    next_post_at = 0.0
    event_loop = asyncio.get_running_loop()
    while True:
        entry, video, state_key, state, pending_ids = await pending_videos.get()
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
                await channel.send(format_silent_post(video["url"]))
                posted_ids.add(video["id"])
            _save_video_state(state, state_key, latest_id or video["id"], posted_ids)
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


async def start_youtube_watcher(
    bot,
) -> None:
    """Poll configured channels and queue newly discovered non-Short videos."""
    await bot.wait_until_ready()
    watches, poll_interval_seconds, post_interval_seconds = _load_watch_config()
    watches = [
        entry for entry in watches
        if isinstance(entry, dict)
        and entry.get("enabled", True)
        and entry.get("username")
        and entry.get("channel_id")
    ]
    if not watches:
        return

    state = _load_state()
    pending_videos = asyncio.Queue()
    pending_ids = set()
    asyncio.create_task(_dispatch_videos(bot, pending_videos, post_interval_seconds))

    while True:
        for entry in watches:
            try:
                handle = entry["username"].strip().lstrip("@")
                state_key = entry.get("name") or handle
                video = await asyncio.to_thread(get_latest_video, handle)
                if not video:
                    continue
                latest_id, posted_ids = _get_video_state(state, state_key)
                _save_video_state(state, state_key, video["id"], posted_ids)
                pending_key = (state_key, video["id"])
                if video["id"] not in posted_ids and pending_key not in pending_ids:
                    pending_ids.add(pending_key)
                    await pending_videos.put((entry, video, state_key, state, pending_ids))
            except Exception:
                continue
        await asyncio.sleep(poll_interval_seconds)