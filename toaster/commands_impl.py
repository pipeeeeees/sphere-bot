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

from toaster.modules.mlb import get_standings


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
    embed.add_field(name="$toast", value="Toggle channel blacklist for Toast to speak in", inline=False)
    embed.add_field(name="$reboot", value="Restart the bot process", inline=False)
    embed.add_field(name="$pull", value="Run git pull and print results", inline=False)
    embed.add_field(name="$mlb_standings", value="Show all MLB division standings", inline=False)
    embed.add_field(name="$mlb_division <division>", value="Show standings for one division (nl-east, al-west, etc.)", inline=False)
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
    Toggle channel blacklist for Toast to speak in.
    Adds or removes the current channel from the blacklist.
    """
    channel_id = ctx.channel.id
    channel_name = ctx.channel.name
    
    blacklist_file = Path("config") / "channel_blacklist.json"
    
    try:
        # Load current blacklist
        if blacklist_file.exists():
            with open(blacklist_file, 'r') as f:
                data = json.load(f)
        else:
            data = {"channels": []}
        
        channels = data.get("channels", [])
        
        # Check if channel is already blacklisted
        existing_entry = None
        for entry in channels:
            if entry.get("id") == channel_id:
                existing_entry = entry
                break
        
        if existing_entry:
            # Remove from blacklist
            channels.remove(existing_entry)
            data["channels"] = channels
            with open(blacklist_file, 'w') as f:
                json.dump(data, f, indent=2)
            await ctx.send(f"✅ Unmuted channel '{channel_name}' (ID: {channel_id})! I can now speak here again.")
        else:
            # Add to blacklist
            new_entry = {"id": channel_id, "nickname": channel_name}
            channels.append(new_entry)
            data["channels"] = channels
            with open(blacklist_file, 'w') as f:
                json.dump(data, f, indent=2)
            await ctx.send(f"🤐 Muted channel '{channel_name}' (ID: {channel_id}). I won't respond here unless mentioned. Use `$toast` again to unmute.")
    
    except Exception as e:
        await ctx.send(f"Sorry, I encountered an error managing the channel blacklist: {str(e)}")


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


async def mlb_all_standings_command(ctx: commands.Context) -> None:
    """
    Print standings for all MLB divisions.
    """
    divisions = [
        (104, 204, "NL East"),
        (104, 205, "NL Central"),
        (104, 203, "NL West"),
        (103, 201, "AL East"),
        (103, 202, "AL Central"),
        (103, 200, "AL West"),
    ]

    all_text = ""
    for league_id, division_id, title in divisions:
        text = get_standings(league_id, division_id, f"{title} Standings")
        all_text += text + "\n"
    await ctx.send(all_text)


async def mlb_division_standings_command(ctx: commands.Context, division: str) -> None:
    """
    Print standings for a specific MLB division by name.
    Usage: $mlb_division <division>
    Examples: $mlb_division nl-east, $mlb_division AL West
    """
    normalized = division.lower().replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "nleast": (104, 204, "NL East"),
        "nlcentral": (104, 205, "NL Central"),
        "nlwest": (104, 203, "NL West"),
        "aleast": (103, 201, "AL East"),
        "alcentral": (103, 202, "AL Central"),
        "alwest": (103, 200, "AL West"),
    }

    if normalized not in mapping:
        await ctx.send(
            "⚠️ Division not recognized. Valid divisions are: NL East, NL Central, NL West, AL East, AL Central, AL West."
        )
        return

    league_id, division_id, title = mapping[normalized]
    text = get_standings(league_id, division_id, f"{title} Standings")
    await ctx.send(text)


# Export all command implementations
__all__ = [
    "hello_command",
    "help_command",
    "ping_command",
    "uptime_command",
    "toast_command",
    "reboot_command",
    "pull_command",
    "mlb_all_standings_command",
    "mlb_division_standings_command"
]
