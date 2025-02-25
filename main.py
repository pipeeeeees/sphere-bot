import os
import json
import logging
import discord
from discord.ext import commands

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Function to read token from file
def read_file(path):
    if not os.path.exists(path):
        logger.error(f"File {path} not found.")
        return None
    with open(path, "r") as file:
        return file.read().strip()

# Function to load JSON lookup table
def read_json(path):
    if not os.path.exists(path):
        logger.error(f"JSON file {path} not found.")
        return {}
    try:
        with open(path, "r") as file:
            return json.load(file)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {path}.")
        return {}

# Load bot token and owner lookup table
TOKEN = read_file("config/token.txt")
OWNERS = read_json("config/user_ids.json")

# Get primary admin ID from lookup table
OWNER_ID = OWNERS.get("pipeeeeees")

if not TOKEN:
    raise ValueError("TOKEN is missing. Check config/token.txt.")

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

bot.run(TOKEN)
