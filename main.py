import os
import io
import json
import logging
import discord
import subprocess
import sys
from discord.ext import commands, tasks
from datetime import datetime
import pytz


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscordHandler(logging.Handler):
    """Custom logging handler to send logs to a Discord channel."""
    
    def __init__(self, bot, channel_id):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    async def send_log(self, message):
        """Send log messages to the specified Discord channel."""
        if not self.bot.is_ready():
            return
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(f"📝 {message}")

    def emit(self, record):
        """Emit logs asynchronously."""
        log_message = self.format(record)
        if self.bot.loop.is_running():
            self.bot.loop.create_task(self.send_log(log_message))

def setup_logging(bot):
    """Attach the custom Discord log handler to the logger."""
    if LOG_CHANNEL_ID:
        discord_handler = DiscordHandler(bot, LOG_CHANNEL_ID)
        discord_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        discord_handler.setFormatter(formatter)
        logger.addHandler(discord_handler)


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
CHANNELS = read_json("config/channel_ids.json")

# ID variables
OWNER_ID = OWNERS.get("pipeeeeees")
LOG_CHANNEL_ID = CHANNELS.get("bot-testing")  # Get the bot-testing channel ID

# Set bot command prefix and enable intents
intents = discord.Intents.default()
intents.message_content = True  
intents.dm_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user}")

    setup_logging(bot)  # Attach logging to Discord

    # Send DM to primary admin if available
    if OWNER_ID:
        try:
            user = await bot.fetch_user(OWNER_ID)
            if user:
                await user.send(f"✅ Bot {bot.user} is online!")
                logger.info(f"✅ Successfully booted!")
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

    #logger.info("✅ Scheduled message system initialized")

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
            target_id = reminder["id"]  # Can be user id or channel id
            message = reminder["message"]

            try:
                # Try fetching as a user
                user = await bot.fetch_user(target_id)
                if user:
                    await user.send(message)
                    #logger.info(f"✅ Sent scheduled message to user {user.name}: {message}")
                    continue  # Skip the channel check if it's a valid user ID

            except discord.NotFound:
                # User not found, assume it's a channel ID and try fetching as a channel
                try:
                    channel = await bot.fetch_channel(target_id)
                    if isinstance(channel, discord.TextChannel):
                        await channel.send(message)
                        #logger.info(f"✅ Sent scheduled message to channel {channel.name}: {message}")
                    else:
                        logger.warning(f"⚠️ Target {target_id} is not a valid text channel.")
                except discord.Forbidden:
                    logger.warning(f"⚠️ Cannot send message to channel {target_id}. Check permissions.")
                except discord.HTTPException as e:
                    logger.error(f"⚠️ Failed to send message to channel {target_id}: {e}")

            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {target_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {target_id}: {e}")

#@bot.command()
#async def add_reminder(ctx, time: str, days: str, user_id: int, *, message: str):
#    """
#    Command to add a new scheduled reminder.
#    Usage: !add_reminder HH:MM "Monday,Tuesday" USER_ID message text
#    Example: !add_reminder 08:00 "Monday,Wednesday,Friday" 123456789012345678 "Time to wake up!"
#    """
#    days_list = [day.strip() for day in days.split(",")]
#
#    # Load current reminders
#    schedule_data = read_json(SCHEDULE_FILE)
#
#    # Append new reminder
#    new_reminder = {
#        "user_id": user_id,
#        "message": message,
#        "time": time,
#        "days": days_list
#    }
#    schedule_data["reminders"].append(new_reminder)
#
#    # Save back to file
#    write_json(SCHEDULE_FILE, schedule_data)
#
#    await ctx.send(f"✅ Reminder added for {time} on {', '.join(days_list)}.")


@bot.event
async def on_message(message):
    # Check if it's a DM (DMChannel) or a guild text channel (TextChannel)
    if isinstance(message.channel, discord.DMChannel):
        channel_name = f"DM with {message.author.name}"  # Label for DMs
    else:
        channel_name = message.channel.name  # Use .name for guild channels

    username = message.author.name

    print(f"Received message in channel '{channel_name}' from '{username}': {message.content}")  # Debugging
    
    # Check if message is from the specific user ID
    if message.author.id == 1343807638227648533:
        await message.channel.send("🔄 Pulling latest updates and restarting...")

        try:
            # Perform Git pull
            process = subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            output = process.stdout + process.stderr
            await message.channel.send(f"📝 Git Pull Output:\n```\n{output}\n```")

            # Restart the bot
            await message.channel.send("✅ Restarting bot...")
            subprocess.Popen([sys.executable, "main.py"])  # Start new bot process
            sys.exit(0)  # Exit the current script

        except subprocess.CalledProcessError as e:
            await message.channel.send(f"❌ Git pull failed:\n```\n{e.output}\n```")
            print(f"Git pull failed: {e}")

    if message.author.bot:
        return  # Ignore bot messages

    if int(message.channel.id) == int(LOG_CHANNEL_ID) and message.content.strip() == "$schedule":
        schedule_data = read_json(SCHEDULE_FILE)
        schedule_text = json.dumps(schedule_data, indent=4)  # Pretty-print JSON

        # Create an in-memory text file and send it
        file = discord.File(io.BytesIO(schedule_text.encode()), filename="schedule.json")
        await message.channel.send("📂 **Schedule file:**", file=file)
        print("✅ Sent schedule file.")

    await bot.process_commands(message)  # Ensure commands still work



# Run the bot
bot.run(TOKEN)
