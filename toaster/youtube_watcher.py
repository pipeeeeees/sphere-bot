"""Background YouTube watcher driven by config/youtube_watch.json."""

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Optional
from xml.etree import ElementTree

import requests


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


def _load_state() -> Dict[str, str]:
    try:
        with STATE_FILE.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        return state if isinstance(state, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


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
    match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]+)"', response.text)
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
        video = await pending_videos.get()
        delay = next_post_at - event_loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            entry, video = video
            channel_id = int(entry["channel_id"])
            channel = bot.get_channel(channel_id)
            if channel is None:
                channel = await bot.fetch_channel(channel_id)
            await channel.send(video["url"])
        except Exception:
            pass
        finally:
            pending_videos.task_done()
        next_post_at = event_loop.time() + post_interval_seconds


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
    asyncio.create_task(_dispatch_videos(bot, pending_videos, post_interval_seconds))

    while True:
        for entry in watches:
            try:
                handle = entry["username"].strip().lstrip("@")
                state_key = entry.get("name") or handle
                video = await asyncio.to_thread(get_latest_video, handle)
                if video and state.get(state_key) is None:
                    state[state_key] = video["id"]
                    _save_state(state)
                elif video and video["id"] != state.get(state_key):
                    await pending_videos.put((entry, video))
                    state[state_key] = video["id"]
                    _save_state(state)
            except Exception:
                continue
        await asyncio.sleep(poll_interval_seconds)