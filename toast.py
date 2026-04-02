"""
Toast Discord Bot - Entry Point
Scalable bot with modular command and scheduler systems.
"""

import discord
from discord.ext import commands
import asyncio
import importlib
from pathlib import Path
from datetime import datetime
import random
import time

from toaster import CommandRegistry, ScheduleRegistry, load_token, get_gemini_response_with_key
from toaster.config import load_config


# Create bot instance
bot = commands.Bot(command_prefix='$', intents=discord.Intents.all())

# Track bot start time for uptime command in shared state module
from toaster.state import set_start_time

# Conversation history storage
conversation_history = {}  # Dict[str, str] - user_id/channel_id -> history string

# Rate limiting for AI responses
last_ai_response = {}  # Dict[str, float] - user_id/channel_id -> timestamp
AI_COOLDOWN_SECONDS = 5  # Minimum seconds between AI responses per conversation

# Initialize registries
command_registry = CommandRegistry()
schedule_registry = ScheduleRegistry()


def get_conversation_key(message: discord.Message) -> str:
    """Get the key for storing conversation history."""
    if isinstance(message.channel, discord.DMChannel):
        return f"user_{message.author.id}"
    else:
        return f"channel_{message.channel.id}"


def update_conversation_history(key: str, user_message: str, ai_response: str) -> None:
    """Update conversation history for a user/channel."""
    global conversation_history
    
    # Initialize if not exists
    if key not in conversation_history:
        conversation_history[key] = ""
    
    # Add to history (keep last 10 exchanges to avoid token limits)
    history_lines = conversation_history[key].split('\n')
    new_lines = [f"User: {user_message}", f"AI: {ai_response}"]
    
    # Keep only last 10 exchanges (20 lines)
    combined_lines = history_lines + new_lines
    if len(combined_lines) > 20:
        combined_lines = combined_lines[-20:]
    
    conversation_history[key] = '\n'.join(combined_lines)


async def handle_dm_response(message: discord.Message) -> None:
    """Handle AI responses to DM messages."""
    if message.author == bot.user:
        return
    
    # Response when AI quota is exceeded
    await message.channel.send("🤖 The bot's AI is currently unavailable (quota exceeded). Try again tomorrow or the owner can upgrade to a paid plan at https://ai.google.dev/pricing")


async def handle_random_channel_response(message: discord.Message) -> None:
    """Handle random AI responses in channels (40% chance)."""
    if message.author == bot.user:
        return
    
    # Skip if 40% chance doesn't trigger
    if random.random() > 0.4:
        return
    
    # Just skip silently when quota is exceeded - don't spam errors in channels
    pass


def load_commands_from_config() -> None:
    """
    Load commands from config/commands.json and register them with the bot.
    Each command entry specifies a module path and function name to import.
    """
    config = load_config("config")
    
    for cmd_config in config["commands"]:
        try:
            name = cmd_config["name"]
            description = cmd_config["description"]
            module_path = cmd_config["module"]
            function_name = cmd_config["function"]
            
            # Dynamically import the module and get the function
            module = importlib.import_module(module_path)
            callback = getattr(module, function_name)
            
            # Register with command registry
            command_registry.register(name, callback, description)
            
            print(f"✓ Loaded command: ${name}")
        except Exception as e:
            print(f"✗ Failed to load command {cmd_config.get('name', 'unknown')}: {e}")


def load_schedules_from_config() -> None:
    """
    Load schedules from config/schedule.json and register them with the scheduler.
    """
    config = load_config("config")
    
    for schedule_config in config["schedules"]:
        try:
            name = schedule_config["name"]
            message = schedule_config["message"]
            channel_id = schedule_config["channel_id"]
            schedule_type = schedule_config["type"]
            time_str = schedule_config["time"]
            enabled = schedule_config.get("enabled", True)
            
            weekdays = schedule_config.get("weekdays")
            date = schedule_config.get("date")
            
            # Register with schedule registry
            schedule_registry.register(
                name=name,
                message=message,
                channel_id=channel_id,
                schedule_type=schedule_type,
                time_str=time_str,
                weekdays=weekdays,
                date=date,
                enabled=enabled
            )
            
            status = "✓" if enabled else "⊘"
            print(f"{status} Loaded schedule: {name}")
        except Exception as e:
            print(f"✗ Failed to load schedule {schedule_config.get('name', 'unknown')}: {e}")


def register_commands_with_bot() -> None:
    """
    Register all commands from the registry with the Discord bot.
    Creates @bot.command() decorators dynamically.
    """
    for cmd_config in command_registry.get_all_commands():
        name = cmd_config["name"]
        callback = cmd_config["callback"]
        
        # Create a bot command from the callback
        bot.add_command(commands.Command(callback, name=name))


@bot.event
async def on_ready() -> None:
    """Handle bot ready event."""
    set_start_time(datetime.now())
    
    print(f'\n✓ Logged in as {bot.user}')
    print(f'✓ Bot is ready to receive commands')
    
    # Start scheduler if there are enabled schedules
    if any(s["enabled"] for s in schedule_registry.get_all_schedules()):
        print('✓ Starting message scheduler...\n')
        asyncio.create_task(schedule_registry.start_scheduler(bot))
    else:
        print()
    
    # Send boot notification DM to owner
    config = load_config("config")
    bot_config = config.get("bot_config", {})
    if bot_config.get("notify_on_boot", False):
        owner_id = bot_config.get("owner_user_id")
        if owner_id:
            try:
                owner = await bot.fetch_user(owner_id)
                await owner.send("🍞 Toast has booted successfully!")
                print(f'✓ Boot notification sent to owner ({owner_id})')
            except discord.NotFound:
                print(f'✗ Failed to send boot notification: User ID {owner_id} not found. Please check your user ID in config/bot_config.json')
                print('  To get your user ID: Enable Developer Mode in Discord, right-click your name, and select "Copy ID"')
            except discord.Forbidden:
                print(f'✗ Failed to send boot notification: Cannot DM user {owner_id}. The user may have DMs disabled or blocked the bot.')
            except Exception as e:
                print(f'✗ Failed to send boot notification: {e}')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Type `$commands` for available commands.")
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}")
        print(f"Command error: {error}")


@bot.event
async def on_message(message: discord.Message) -> None:
    """Handle all messages for AI responses."""
    # Process commands first
    await bot.process_commands(message)
    
    # Skip if message is from bot
    if message.author == bot.user:
        return

    # If this is a command invocation (starts with the command prefix), do not trigger LLM responses
    if message.content.startswith('$'):
        return
    
    try:
        # Handle DMs with AI responses
        if isinstance(message.channel, discord.DMChannel):
            await handle_dm_response(message)
        
        # Handle random channel responses (only in guilds, not DMs)
        elif message.guild:
            await handle_random_channel_response(message)
            
    except Exception as e:
        print(f"Error in message handling: {e}")


def initialize_bot() -> None:
    """Initialize bot by loading configuration and registering commands."""
    print("Loading Toast Bot configuration...\n")
    
    # Load commands and schedules from config files
    load_commands_from_config()
    load_schedules_from_config()
    
    # Register commands with the bot
    print()
    register_commands_with_bot()


def main() -> None:
    """Main entry point for the bot."""
    initialize_bot()
    
    # Load token and run bot
    print()
    TOKEN = load_token("config")
    bot.run(TOKEN)


# Initialize on module load so registries are populated for testing/imports
initialize_bot()


if __name__ == "__main__":
    # Re-initialize in case configuration changed, then run bot
    TOKEN = load_token("config")
    bot.run(TOKEN)
