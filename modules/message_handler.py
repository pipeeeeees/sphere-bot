import json
import io
import discord
import logging
import datetime

from modules import pollen

logger = logging.getLogger(__name__)
start_time = datetime.datetime.now()

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
    """Handles messages for the bot"""

    # if $schedule is sent in the bot-testing channel, send the schedule file
    if message.content.strip() == "$schedule" and int(message.channel.id) == int(log_channel_id):
        schedule_data = read_json(SCHEDULE_FILE)
        schedule_text = json.dumps(schedule_data, indent=4)

        file = discord.File(io.BytesIO(schedule_text.encode()), filename="schedule.json")
        await message.channel.send("📂 **Schedule file:**", file=file)
        logger.info("✅ Sent schedule file.")

    
    # if $uptime is sent, send the uptime
    if message.content.strip() == "$uptime":
        current_time = datetime.datetime.now()
        uptime = current_time - start_time
        await message.channel.send(f"⏳ **Uptime:** {uptime}")
        logger.info("✅ Sent uptime.")

    # if $pollen is sent, send the pollen count
    if message.content.strip() == "$pollen":
        pollen_count = pollen.get_atl_pollen_count()
        if type(pollen_count) == int:
            await message.channel.send(f"🌼 **Pollen count:** {pollen_count}")
            logger.info("✅ Sent pollen count.")
        elif pollen_count == None:
            await message.channel.send("❌ **Pollen count not reported.**")
            logger.info("❌ Pollen count not reported.")
        elif pollen_count == 'HTML Failure':
            await message.channel.send("❌ **HTML Parsing Error.**")
            logger.info("❌ HTML Parsing Error.")
