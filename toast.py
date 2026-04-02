"""
Toast Discord Bot - Entry Point
Scalable bot with modular command and scheduler systems.
"""

import discord
from discord.ext import commands
import asyncio
import importlib
from pathlib import Path

from toaster import CommandRegistry, ScheduleRegistry, load_token
from toaster.config import load_config


# Create bot instance
bot = commands.Bot(command_prefix='$', intents=discord.Intents.all())

# Initialize registries
command_registry = CommandRegistry()
schedule_registry = ScheduleRegistry()


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
            
            print(f"✓ Loaded command: !{name}")
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
    print(f'\n✓ Logged in as {bot.user}')
    print(f'✓ Bot is ready to receive commands')
    
    # Start scheduler if there are enabled schedules
    if any(s["enabled"] for s in schedule_registry.get_all_schedules()):
        print('✓ Starting message scheduler...\n')
        asyncio.create_task(schedule_registry.start_scheduler(bot))
    else:
        print()


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Type `!help` for available commands.")
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}")
        print(f"Command error: {error}")


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
