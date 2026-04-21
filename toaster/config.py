"""
Configuration Loader
Centralizes loading of bot configuration from JSON files.
"""

import json
from pathlib import Path
from typing import Dict, Any


def load_config(config_path: str = "config") -> Dict[str, Any]:
    """
    Load all configuration from the config folder.
    
    Args:
        config_path: Path to config folder (default: "config")
        
    Returns:
        Dictionary with 'token', 'commands', and 'schedules' keys
    """
    config_dir = Path(config_path)
    
    result = {
        "token": None,
        "commands": [],
        "schedules": [],
        "bot_config": {}
    }
    
    # Load token
    token_file = config_dir / "toast_discord_bot_token.json"
    if token_file.exists():
        with open(token_file, 'r') as f:
            token_data = json.load(f)
            result["token"] = token_data.get("token")
    
    # Load commands
    commands_file = config_dir / "commands.json"
    if commands_file.exists():
        with open(commands_file, 'r') as f:
            result["commands"] = json.load(f)
    
    # Load schedules
    schedules_file = config_dir / "schedule.json"
    if schedules_file.exists():
        with open(schedules_file, 'r') as f:
            result["schedules"] = json.load(f)
    
    # Load bot config
    bot_config_file = config_dir / "bot_config.json"
    if bot_config_file.exists():
        with open(bot_config_file, 'r') as f:
            result["bot_config"] = json.load(f)
    
    return result


def load_token(config_path: str = "config") -> str:
    """
    Load just the Discord bot token.
    
    Args:
        config_path: Path to config folder
        
    Returns:
        Discord bot token string
        
    Raises:
        FileNotFoundError: If token file doesn't exist
        KeyError: If token key doesn't exist in file
    """
    config = load_config(config_path)
    if not config["token"]:
        raise FileNotFoundError("Bot token not found in config/toast_discord_bot_token.json")
    return config["token"]


def load_channel_blacklist(config_path: str = "config") -> list:
    """
    Load blacklisted channel definitions for random AI responses.

    Args:
        config_path: Path to config folder

    Returns:
        List of channel entries with keys 'id' (int) and 'nickname' (str|None).
    """
    try:
        blacklist_file = Path(config_path) / "channel_blacklist.json"
        if blacklist_file.exists():
            with open(blacklist_file, 'r') as f:
                data = json.load(f)

                channels = data.get("channels", [])
                result = []

                for entry in channels:
                    if isinstance(entry, int):
                        result.append({"id": entry, "nickname": None})
                    elif isinstance(entry, dict):
                        channel_id = entry.get("id")
                        if channel_id is None:
                            continue
                        nickname = entry.get("nickname") or entry.get("name")
                        result.append({"id": int(channel_id), "nickname": nickname})

                return result
        return []
    except Exception as e:
        print(f"Error loading channel blacklist: {e}")
        return []


def get_channel_blacklist_ids(config_path: str = "config") -> set:
    """
    Get a set of blacklisted channel IDs for quick membership checks.
    """
    return {entry["id"] for entry in load_channel_blacklist(config_path)}
