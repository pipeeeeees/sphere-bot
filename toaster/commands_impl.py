"""
Command Implementations
Contains all callback functions for registered commands.
Each function must be async and accept a discord.ext.commands.Context parameter.
"""

import discord
from discord.ext import commands


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
    embed.add_field(name="!hello", value="Greet the bot", inline=False)
    embed.add_field(name="!help", value="Show this help message", inline=False)
    await ctx.send(embed=embed)


async def ping_command(ctx: commands.Context) -> None:
    """
    Check bot latency.
    """
    await ctx.send(f'🏓 Pong! {round(ctx.bot.latency * 1000)}ms')


# Export all command implementations
__all__ = [
    "hello_command",
    "help_command",
    "ping_command"
]
