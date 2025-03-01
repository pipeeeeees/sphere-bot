import json
import io
import discord
import logging
import datetime
import random
import asyncio
import subprocess
import sys

from modules import pollen
from modules import weather
from modules import report

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

    # if the message is a DM to the bot, send it to user 326676188057567232
    if message.guild == None:
        user = bot.get_user(326676188057567232)
        await user.send(f"📬 **{message.author}** sent a DM to Sphere:\n{message.content}")
        #logger.info(f"📬 **{message.author}** sent a DM:\n{message.content}")

    # if $schedule is sent in the bot-testing channel, send the schedule file
    if message.content.strip() == "$schedule" and int(message.channel.id) == int(log_channel_id):
        schedule_data = read_json(SCHEDULE_FILE)
        schedule_text = json.dumps(schedule_data, indent=4)

        file = discord.File(io.BytesIO(schedule_text.encode()), filename="schedule.json")
        await message.channel.send("📂 **Schedule file:**", file=file)
        logger.info("✅ Sent schedule file.")

    
    # if $uptime is sent, send the uptime
    elif message.content.strip() == "$uptime":
        current_time = datetime.datetime.now()
        uptime_seconds = (current_time - start_time).total_seconds()

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)

        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"
        
        await message.channel.send(f"⏳ Uptime: **{uptime_str}**")
        logger.info(f"✅ Sent uptime: {uptime_str}")

    # if $pollen is sent, send the pollen count
    elif message.content.strip() == "$pollen":
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

    # if $report is sent, send the morning report
    elif message.content.strip() == "$report":
        report_str = report.get_morning_report()
        await message.channel.send(report_str)
        logger.info("✅ Sent morning report.")

    # if a Trae Young tweet is detected, send a message
    elif "https://fixvx.com/TheTraeYoung/status/" in message.content:
        # a 1 in 3 chance to send a message
        result = random.randint(1, 100)
        if result < 20:
            await message.channel.send("🗣️🗣️🗣️ **Trae Young Tweeted** 🗣️🗣️🗣️")
            logger.info("✅ Sent The Trae Young message.")
        #elif result == 2:
        #    # wait for 10 seconds
        #    await asyncio.sleep(10)
        #    await message.channel.send("Fuck Trae Young")
        #    logger.info("✅ Sent The Trae Young message.")

    # if $pull is sent, git pull
    elif message.content.strip() == "$pull":
        try:
            process = subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            output = process.stdout + process.stderr
            await message.channel.send(f"📝 Git Pull Output:\n```\n{output}\n```")
        except subprocess.CalledProcessError as e:
            await message.channel.send(f"❌ Git pull failed:\n```\n{e.output}\n```")
            print(f"Git pull failed: {e}")

    # if $reboot is sent, reboot
    elif message.content.strip() == "$reboot":
        subprocess.Popen([sys.executable, "main.py"])  # Start new bot process
        sys.exit(0)  # Exit the current script
