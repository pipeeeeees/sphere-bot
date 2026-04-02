"""
Command Implementations
Contains all callback functions for registered commands.
Each function must be async and accept a discord.ext.commands.Context parameter.
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys


async def hello_command(ctx: commands.Context) -> None:
    """
    Friendly greeting command.
    """
    await ctx.send('Hello! I am Toast, your friendly Discord bot.')


async def help_command(ctx: commands.Context) -> None:
    """
    Display available commands.
    Note: This is an example. In production, you'd want to make this dynamic
    based on the CommandRegistry to list all registered commands.
    """
    embed = discord.Embed(
        title="Toast Bot Commands",
        description="Here are the available commands:",
        color=discord.Color.gold()
    )
    embed.add_field(name="$hello", value="Greet the bot", inline=False)
    embed.add_field(name="$commands", value="Show this help message", inline=False)
    embed.add_field(name="$ping", value="Check bot latency", inline=False)
    embed.add_field(name="$uptime", value="Display bot uptime", inline=False)
    embed.add_field(name="$toast", value="Toggle channel whitelist for Toast to speak in", inline=False)
    embed.add_field(name="$reboot", value="Restart the bot process", inline=False)
    embed.add_field(name="$pull", value="Run git pull and print results", inline=False)
    await ctx.send(embed=embed)


async def ping_command(ctx: commands.Context) -> None:
    """
    Check bot latency.
    """
    await ctx.send(f'🏓 Pong! {round(ctx.bot.latency * 1000)}ms')


async def uptime_command(ctx: commands.Context) -> None:
    """
    Display bot uptime.
    """
    from toaster.state import get_start_time

    start_time = get_start_time()
    if start_time is None:
        await ctx.send("⏰ Bot uptime not available")
        return
    
    uptime = datetime.now() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_str = ""
    if days > 0:
        uptime_str += f"{days}d "
    if hours > 0 or days > 0:
        uptime_str += f"{hours}h "
    if minutes > 0 or hours > 0 or days > 0:
        uptime_str += f"{minutes}m "
    uptime_str += f"{seconds}s"
    
    await ctx.send(f"⏰ Bot has been online for: {uptime_str}")


async def toast_command(ctx: commands.Context) -> None:
    """
    Toggle channel whitelist for Toast to speak in.
    Adds or removes the current channel from the whitelist.
    """
    channel_id = ctx.channel.id
    channel_name = ctx.channel.name
    
    whitelist_file = Path("config") / "channel_whitelist.json"
    
    try:
        # Load current whitelist
        if whitelist_file.exists():
            with open(whitelist_file, 'r') as f:
                data = json.load(f)
        else:
            data = {"channels": []}
        
        channels = data.get("channels", [])
        
        # Check if channel is already whitelisted
        existing_entry = None
        for entry in channels:
            if entry.get("id") == channel_id:
                existing_entry = entry
                break
        
        if existing_entry:
            # Remove from whitelist
            channels.remove(existing_entry)
            data["channels"] = channels
            with open(whitelist_file, 'w') as f:
                json.dump(data, f, indent=2)
            await ctx.send(f"Removed channel '{channel_name}' (ID: {channel_id}) from my list of channels to speak in. Use $toast again to add it back.")
        else:
            # Add to whitelist
            new_entry = {"id": channel_id, "nickname": channel_name}
            channels.append(new_entry)
            data["channels"] = channels
            with open(whitelist_file, 'w') as f:
                json.dump(data, f, indent=2)
            await ctx.send(f"Added channel '{channel_name}' (ID: {channel_id}) to my list of channels to speak in! I can now respond with AI messages here.")
    
    except Exception as e:
        await ctx.send(f"Sorry, I encountered an error managing the channel whitelist: {str(e)}")


async def reboot_command(ctx: commands.Context) -> None:
    """
    Restart the bot process.
    """
    try:
        await ctx.send("🔄 **Rebooting...**")
        script_path = Path(__file__).resolve().parents[1] / "toast.py"
        subprocess.Popen([sys.executable, str(script_path)])
        sys.exit(0)
    except Exception as e:
        await ctx.send(f"⚠️ Failed to reboot bot: {str(e)}")


async def pull_command(ctx: commands.Context) -> None:
    """
    Perform a git pull in the bot repository and report output.
    """
    try:
        process = subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
        output = (process.stdout or "") + (process.stderr or "")
        if not output:
            output = "Git pull completed with no output."
        await ctx.send(f"📝 Git Pull Output:\n```\n{output}\n```")
    except subprocess.CalledProcessError as e:
        error_output = (e.stdout or "") + (e.stderr or "")
        if not error_output:
            error_output = str(e)
        await ctx.send(f"❌ Git pull failed:\n```\n{error_output}\n```")
        print(f"Git pull failed: {e}")


# Export all command implementations
__all__ = [
    "hello_command",
    "help_command",
    "ping_command",
    "uptime_command",
    "toast_command",
    "reboot_command",
    "pull_command"
]
