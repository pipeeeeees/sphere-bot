import json
import discord
from discord.ext import commands

# Function to read token from file
def read_file(path):
    with open(path, "r") as file:
        return file.read().strip()

# Function to load JSON lookup table
def read_json(path):
    with open(path, "r") as file:
        return json.load(file)

# Load token and owner lookup table
TOKEN = read_file("config/token.txt")
OWNERS = read_json("config/user_ids.json")

# Get primary admin ID from lookup table
OWNER_ID = OWNERS.get("pipeeeeees")

# Set bot command prefix
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Send DM to primary admin
    if OWNER_ID:
        user = await bot.fetch_user(OWNER_ID)
        try:
            await user.send(f"✅ Bot {bot.user} has logged in!")
        except discord.Forbidden:
            print("Bot cannot send a DM. Enable DMs from server members.")

bot.run(TOKEN)
