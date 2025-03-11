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

from modules.message_handler import handle_message 
from modules import report
from modules import pollen

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

# read all json config files
OWNERS = read_json("config/user_ids.json")
CHANNELS = read_json("config/channel_ids.json")
TOKEN = read_json("config/token.json").get("token")
if not TOKEN:
    raise ValueError("TOKEN is missing. Check config/token.json.")

# ID variables
OWNER_ID = OWNERS.get("pipeeeeees")             # my discord user ID
LOG_CHANNEL_ID = CHANNELS.get("bot-testing")    # bot-testing channel ID

# Set bot command prefix and enable intents
intents = discord.Intents.default()
intents.message_content = True  
intents.dm_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, heartbeat_timeout=6000)

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
                #logger.info(f"✅ Successfully booted!")
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
    pollen_data = read_json("config/pollen_sub.json")
    morning_report_data = read_json("config/morning_report_sub.json")

    # Send regular scheduled messages
    for reminder in schedule_data.get("reminders", []):
        if current_time == reminder["time"] and current_day in reminder["days"]:
            target_id = reminder["id"]  # Can be user id or channel id
            message = reminder["message"]

            try:
                # Try fetching as a user
                user = await bot.fetch_user(target_id)
                if user:
                    await user.send(message)
                    continue  # Skip the channel check if it's a valid user ID

            except discord.NotFound:
                # User not found, assume it's a channel ID and try fetching as a channel
                try:
                    channel = await bot.fetch_channel(target_id)
                    if isinstance(channel, discord.TextChannel):
                        if target_id in [1079612189175988264, 1344165418885054534]:
                            if message == "[morningreport]":
                                message = report.get_morning_report()
                                await channel.send(message)
                            elif message == "[alert]":
                                weather_alert = report.get_weather_alerts()
                                if weather_alert is not None:
                                    await channel.send(weather_alert)
                        else:
                            await channel.send(message)
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

    # Send pollen subscription messages
    if current_time == pollen_data.get("time") and current_day in pollen_data.get("days", []):
        # if today is wednesday in the month of march, april or may, generate the pollen plot
        if now.month in [3, 4, 5] and now.strftime("%A") == "Wednesday":
            # start date is february 1st of this year
            start_date = datetime(now.year, 2, 1).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")
            await pollen.plot_pollen_counts(start_date, end_date)

        for user_id in pollen_data.get("subscribers", []):
            try:
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f"{pollen.result_handler()}\nTo unsubscribe from pollen alerts at any time, send `$sub pollen`.")
                    if now.month in [3, 4, 5] and now.strftime("%A") == "Wednesday":
                        await user.send(file=discord.File("plots/plot.png"))
                        await user.send(f"📊 It's Wednesday! Here is a plot of the pollen count for the current pollen season.\n Send `$pollen plot {now.year}-01-01 {end_date}` to see the year to date.")
            except discord.NotFound:
                logger.warning(f"⚠️ User {user_id} not found.")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {user_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {user_id}: {e}")

    # Send morning report messages
    if current_time == morning_report_data.get("time") and current_day in morning_report_data.get("days", []):
        for user_id in morning_report_data.get("subscribers", []):
            try:
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f"{report.get_morning_report()}\nTo unsubscribe from the morning report at any time, send `$sub morning report`.")
            except discord.NotFound:
                logger.warning(f"⚠️ User {user_id} not found.")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {user_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {user_id}: {e}")


@bot.event
async def on_message(message):
    # Check if message is from the GitHub Webhook ID
    if message.author.id == 1343807638227648533:
        #await message.channel.send("🔄 Pulling latest updates and restarting...")

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

    # Ignore bot messages
    if message.author.bot:
        return  
    
    # Create a debugging log for all messages
    if isinstance(message.channel, discord.DMChannel):
        channel_name = f"DM with {message.author.name}"  # Label for DMs
    else:
        channel_name = message.channel.name  # Use .name for guild channels

    username = message.author.name

    print(f"Received message in channel '{channel_name}' from '{username}': {message.content}")  # Debugging
    
    await handle_message(bot, message, LOG_CHANNEL_ID)

    await bot.process_commands(message)  # Ensure commands still work

# Run the bot
bot.run(TOKEN)
