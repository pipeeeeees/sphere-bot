import os
import json
import logging
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEDULE_FILE = "config/schedule.json"

# Function to read JSON file
def read_json(path):
    if not os.path.exists(path):
        logger.error(f"JSON file {path} not found.")
        return {"reminders": []}
    try:
        with open(path, "r") as file:
            return json.load(file)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {path}.")
        return {"reminders": []}

# Function to write JSON file (used for adding new reminders)
def write_json(path, data):
    with open(path, "w") as file:
        json.dump(data, file, indent=4)

# Load bot token
TOKEN = read_json("config/token.json").get("token")
if not TOKEN:
    raise ValueError("TOKEN is missing. Check config/token.json.")
OWNERS = read_json("config/user_ids.json")

# Get primary admin ID from lookup table
OWNER_ID = OWNERS.get("pipeeeeees")

# Set bot command prefix and enable intents
intents = discord.Intents.default()
intents.dm_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user}")

    # Send DM to primary admin if available
    if OWNER_ID:
        try:
            user = await bot.fetch_user(OWNER_ID)
            if user:
                await user.send(f"✅ Bot {bot.user} has logged in!")
                logger.info(f"✅ DM sent to {user.name}")
            else:
                logger.warning("Could not fetch user")
        except discord.Forbidden:
            logger.warning("⚠️ Bot cannot send a DM. Enable DMs from server members.")
        except discord.HTTPException as e:
            logger.error(f"⚠️ Failed to send DM: {e}")
    else:
        logger.warning("⚠️ OWNER_ID is not set or invalid")

    # Start the scheduled message task
    if not send_scheduled_messages.is_running():
        send_scheduled_messages.start()

    logger.info("✅ Scheduled message system initialized")

@tasks.loop(minutes=1)  # Check every minute
async def send_scheduled_messages():
    """Sends scheduled messages based on the config file."""
    est = pytz.timezone("America/New_York")
    now = datetime.now(est)
    current_time = now.strftime("%H:%M")  # Format HH:MM
    current_day = now.strftime("%A")  # Get full day name

    schedule_data = read_json(SCHEDULE_FILE)

    for reminder in schedule_data.get("reminders", []):
        if current_time == reminder["time"] and current_day in reminder["days"]:
            user_id = reminder["user_id"]
            message = reminder["message"]

            try:
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(message)
                    logger.info(f"✅ Sent scheduled message to {user.name}: {message}")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {user_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {user_id}: {e}")

@bot.command()
async def add_reminder(ctx, time: str, days: str, user_id: int, *, message: str):
    """
    Command to add a new scheduled reminder.
    Usage: !add_reminder HH:MM "Monday,Tuesday" USER_ID message text
    Example: !add_reminder 08:00 "Monday,Wednesday,Friday" 123456789012345678 "Time to wake up!"
    """
    days_list = [day.strip() for day in days.split(",")]

    # Load current reminders
    schedule_data = read_json(SCHEDULE_FILE)

    # Append new reminder
    new_reminder = {
        "user_id": user_id,
        "message": message,
        "time": time,
        "days": days_list
    }
    schedule_data["reminders"].append(new_reminder)

    # Save back to file
    write_json(SCHEDULE_FILE, schedule_data)

    await ctx.send(f"✅ Reminder added for {time} on {', '.join(days_list)}.")

# Run the bot
bot.run(TOKEN)
