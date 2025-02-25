# package imports
import discord
from discord.ext import commands

# local import the key
import keys
TOKEN = keys.SPHERE_API_KEY

# Set bot command prefix
bot = commands.Bot(command_prefix="$", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def hello(ctx):
    await ctx.send("Hello! 👋")

bot.run(TOKEN)