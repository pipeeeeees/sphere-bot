"""
Command Implementations
Contains all callback functions for registered commands.
Each function must be async and accept a discord.ext.commands.Context parameter.
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta


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


# Export all command implementations
__all__ = [
    "hello_command",
    "help_command",
    "ping_command",
    "uptime_command"
]
