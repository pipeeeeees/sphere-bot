import os
import io
import json
import logging
import asyncio
import discord
import subprocess
import sys
import socket
from discord.ext import commands, tasks
from datetime import datetime
import pytz

from modules.message_handler import handle_message 
from modules import report
from modules import pollen
from modules import mlb
from modules import nba
from modules import epic_games

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

# Function to write JSON file
def write_json(path, data):
    with open(path, "w") as file:
        json.dump(data, file, indent=4)

# read all json config files
OWNERS = read_json("config/user_ids.json")
CHANNELS = read_json("config/channel_ids.json")
TOKEN = read_json("config/token.json").get("token")
GEMINI_API_KEY = read_json("config/token.json").get("gemini")

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

    # Get the hostname of the machine
    hostname = socket.gethostname()

    if not send_scheduled_messages.is_running():
        send_scheduled_messages.start()

    if OWNER_ID:
        try:
            user = await bot.fetch_user(OWNER_ID)
            if user:
                await user.send(f"✅ Bot {bot.user} is online from the machine: {hostname}")
        except discord.Forbidden:
            logger.warning("⚠️ Bot cannot send a DM. Enable DMs from server members.")
        except discord.HTTPException as e:
            logger.error(f"⚠️ Failed to send DM: {e}")
    else:
        logger.warning("⚠️ OWNER_ID is not set or invalid")

    # Start the scheduled message task
    #bot.loop.create_task(minute_checker())

schedule_data = read_json(SCHEDULE_FILE)
pollen_data = read_json("config/pollen_sub.json")
morning_report_data = read_json("config/morning_report_sub.json")
nl_east_data = read_json("config/nl_east_sub.json")
free_game_data = read_json("config/free_epic_game_of_the_week_sub.json")

last_run_minute = None  # Tracks the last minute the task executed

@tasks.loop(seconds=10)
async def send_scheduled_messages():
    """Sends scheduled messages based on the config file."""
    global last_run_minute
    est = pytz.timezone("America/New_York")
    now = datetime.now(est)
    current_time = now.strftime("%H:%M")  # Format HH:MM
    current_day = now.strftime("%A")  # Get full day name
    current_minute = now.strftime("%Y-%m-%d %H:%M")

    status_log = f"🕒 `{now.strftime('%Y-%m-%d %H:%M:%S')}`"
    status_channel = await bot.fetch_channel(1368787921653731339)
    
    
    #status_log = f"Status:\n"

    if last_run_minute == current_minute:
        status_log += " Already ran this minute. Skipping...\n"
        await status_channel.send(status_log.strip())
    else:
        await status_channel.send(status_log.strip())
        last_run_minute = current_minute

        

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
                        #status_log += f"✅ Sent DM to user `{target_id}` with message: `{message}`\n"
                        continue

                except discord.NotFound:
                    # User not found, assume it's a channel ID and try fetching as a channel
                    try:
                        channel = await bot.fetch_channel(target_id)
                        if isinstance(channel, discord.TextChannel):
                            if target_id in [1079612189175988264, 1344165418885054534, 1010706336905961593, 924430124366045214]:
                                if message == "[morningreport]":
                                    message = report.get_morning_report()
                                    await channel.send(message)
                                    #status_log += f"\t✅ Sent morning report to channel `{target_id}`\n"


                                elif message == "[alert]":
                                    weather_alert = report.get_weather_alerts()
                                    if weather_alert is not None:
                                        await channel.send(weather_alert)
                                        #status_log += f"\t✅ Sent weather alert to channel `{target_id}`\n"


                                elif message == "[nleast]":
                                    if now.month >= 4 and now.month < 10:
                                        message = mlb.get_standings(104, 204, "NL East Standings")
                                        message += "\n To see all MLB standings, send `$standings all` at any time."
                                        await channel.send(message)
                                        #status_log += f"\t✅ Sent NL East standings to `{target_id}`\n"


                                elif message == "[allmlb]":
                                    if now.month >= 4 and now.month < 10:
                                        nl_east_str     = mlb.get_standings(104, 204, "NL East Standings")
                                        nl_west_str     = mlb.get_standings(104, 205, "NL Central Standings")
                                        nl_central_str  = mlb.get_standings(104, 203, "NL West Standings")
                                        al_east_str     = mlb.get_standings(103, 201, "AL East Standings")
                                        al_west_str     = mlb.get_standings(103, 202, "AL Central Standings")
                                        al_central_str  = mlb.get_standings(103, 200, "AL West Standings")   
                                        all_standings_str = f"Here are the current MLB Standings:\n{nl_east_str}\n{nl_west_str}\n{nl_central_str}\n{al_east_str}\n{al_west_str}\n{al_central_str}"
                                        await channel.send(all_standings_str)
                                        #status_log += f"\t✅ Sent all MLB standings to `{target_id}`\n"


                                elif message == "[allnba]":
                                    if now.month <= 3 or now.month >= 10:
                                        east_str = nba.get_nba_standings("Eastern Conference Standings", "East")
                                        west_str = nba.get_nba_standings("Western Conference Standings", "West")
                                        all_standings_str = f"{east_str}\n{west_str}"
                                        await channel.send(all_standings_str)
                                        #status_log += f"\t✅ Sent all NBA standings to `{target_id}`\n"


                            else:
                                await channel.send(message)
                                #status_log += f"\t✅ Sent scheduled message to channel `{target_id}`: `{message}`\n"
                        else:
                            logger.warning(f"⚠️ Target {target_id} is not a valid text channel.")
                    except discord.Forbidden:
                        logger.warning(f"⚠️ Cannot send message to channel {target_id}. Check permissions.")
                        #status_log += f"\t❌ Forbidden: Can't send to channel `{target_id}`\n"
                    except discord.HTTPException as e:
                        logger.error(f"⚠️ Failed to send message to channel {target_id}: {e}")
                        #status_log += f"\t❌ HTTP Error sending to channel `{target_id}`: {e}\n"

                except discord.Forbidden:
                    logger.warning(f"⚠️ Cannot send DM to user {target_id}. Check permissions.")
                    #status_log += f"\t❌ Forbidden: Can't DM user `{target_id}`\n"
                except discord.HTTPException as e:
                    logger.error(f"⚠️ Failed to send message to {target_id}: {e}")
                    #status_log += f"\t❌ HTTP Error sending DM to `{target_id}`: {e}\n"

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
                    the_return = pollen.result_handler()
                    if "The pollen count in Atlanta for the day is" in the_return:
                        await user.send(f"{pollen.result_handler()}\n\nTo unsubscribe from pollen alerts at any time, send `$sub pollen`.")
                        if now.month in [3, 4, 5] and now.strftime("%A") == "Wednesday":
                            await user.send(file=discord.File("plots/plot.png"))
                            await user.send(f"📊 It's Wednesday! Here is a plot of the pollen count for the current pollen season.\n\nSend `$pollen plot {now.year}-01-01 {end_date}` to see the year to date.")
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
                    await user.send(f"{report.get_morning_report()}\n\nTo unsubscribe from the morning report at any time, send `$sub morning report`.")
            except discord.NotFound:
                logger.warning(f"⚠️ User {user_id} not found.")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {user_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {user_id}: {e}")

    # Send nl east standings messages
    if current_time == nl_east_data.get("time") and current_day in nl_east_data.get("days", []) and now.month >= 4 and now.month < 10:
        for user_id in nl_east_data.get("subscribers", []):
            try:
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f"{mlb.get_nl_east_standings()}\n\nTo unsubscribe from the NL East standings at any time, send `$sub nl east`.")
            except discord.NotFound:
                logger.warning(f"⚠️ User {user_id} not found.")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {user_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {user_id}: {e}")

    # Send free epic game of the week messages
    if current_time == free_game_data.get("time") and current_day in free_game_data.get("days", []):
        for user_id in free_game_data.get("subscribers", []):
            try:
                user = await bot.fetch_user(user_id)
                if user:
                    url = r"https://store.epicgames.com/en-US/free-games"
                    await user.send(f"The Epic Games Free Game of the Week is **{epic_games.get_latest_free_game()}**. Get it today: {url}\n\nTo unsubscribe from the free Epic Game of the Week at any time, send `$sub free epic games`.")
            except discord.NotFound:
                logger.warning(f"⚠️ User {user_id} not found.")
            except discord.Forbidden:
                logger.warning(f"⚠️ Cannot send DM to user {user_id}. Check permissions.")
            except discord.HTTPException as e:
                logger.error(f"⚠️ Failed to send message to {user_id}: {e}")
    

#async def minute_checker():
#    """Custom loop to check and run send_scheduled_messages every minute."""
#    last_minute = None
#    est = pytz.timezone("America/New_York")
#    
#    while True:
#        now = datetime.now(est)
#        current_minute = now.strftime("%H:%M")
#        
#        # Run the task only when the minute changes
#        if current_minute != last_minute:
#            last_minute = current_minute
#            await send_scheduled_messages()
#        
#        # Sleep until the next second to avoid busy-waiting
#        await asyncio.sleep(1 - (now.microsecond / 1000000))  # Sleep until the next second

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
    
    await handle_message(bot, message, LOG_CHANNEL_ID, GEMINI_API_KEY)

    await bot.process_commands(message)  # Ensure commands still work

# Run the bot
bot.run(TOKEN)
