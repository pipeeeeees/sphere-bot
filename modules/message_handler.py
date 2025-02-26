import json
import io
import discord
import logging

logger = logging.getLogger(__name__)

SCHEDULE_FILE = "config/schedule.json"

def read_json(path):
    """Reads a JSON file and returns its contents."""
    try:
        with open(path, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error(f"Error reading {path}.")
        return {"reminders": []}

async def handle_message(bot, message, log_channel_id):
    """Handles messages for the bot, including the $schedule command."""
    if message.content.strip() == "$schedule" and int(message.channel.id) == int(log_channel_id):
        schedule_data = read_json(SCHEDULE_FILE)
        schedule_text = json.dumps(schedule_data, indent=4)

        file = discord.File(io.BytesIO(schedule_text.encode()), filename="schedule.json")
        await message.channel.send("📂 **Schedule file:**", file=file)
        logger.info("✅ Sent schedule file.")
