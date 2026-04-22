"""
Toast Discord Bot - Entry Point
Scalable bot with modular command and scheduler systems.
"""

import discord
from discord.ext import commands
import asyncio
import importlib
from pathlib import Path
from datetime import datetime, timedelta
import random
import time

from toaster import CommandRegistry, ScheduleRegistry, load_token, get_gemini_response_with_key, get_grok_response_with_key
from toaster.config import load_config, load_channel_blacklist


# Create bot instance
bot = commands.Bot(command_prefix='$', intents=discord.Intents.all())

# Track bot start time for uptime command in shared state module
from toaster.state import set_start_time

# Conversation history storage
conversation_history = {}  # Dict[str, str] - user_id/channel_id -> history string

# Mute state storage for channels/DMs
muted_threads = {}  # Dict[int, datetime] -> unmute time
MUTE_DURATION_SECONDS = 60 * 60 * 3  # 3 hours

# Rate limiting for AI responses
last_ai_response = {}  # Dict[str, float] - user_id/channel_id -> timestamp
AI_COOLDOWN_SECONDS = 5  # Minimum seconds between AI responses per conversation

# Initialize registries
command_registry = CommandRegistry()
schedule_registry = ScheduleRegistry()

# Track loaded commands and schedules for boot notification
loaded_commands = []  # List of (name, success, error_msg)
loaded_schedules = []  # List of (name, success, error_msg)


# AI Provider Configuration
# Options: "grok", "gemini"
AI_PROVIDER = "gemini"


async def get_ai_response(history: str, message: str) -> str:
    """
    Get AI response using the configured provider.
    Can be easily swapped between "grok" and "gemini" by changing AI_PROVIDER.
    
    Args:
        history: Conversation history
        message: User message
        
    Returns:
        AI response text or None if all providers fail
    """
    if AI_PROVIDER == "grok":
        return get_grok_response_with_key(history, message, "config")
    elif AI_PROVIDER == "gemini":
        return get_gemini_response_with_key(history, message, "config")
    else:
        print(f"Unknown AI provider: {AI_PROVIDER}")
        return None


def is_channel_muted(channel_id: int) -> bool:
    """Return True if channel/DM is currently muted."""
    unmute_time = muted_threads.get(channel_id)
    if not unmute_time:
        return False
    if datetime.now() >= unmute_time:
        muted_threads.pop(channel_id, None)
        return False
    return True


def mute_channel(channel_id: int, seconds: int = MUTE_DURATION_SECONDS) -> None:
    """Mute a channel/DM for `seconds`."""
    muted_threads[channel_id] = datetime.now() + timedelta(seconds=seconds)


def is_shutup_command(message: str) -> bool:
    """Detect explicit quiet commands."""
    text = message.lower().strip()
    if "$shutup" in text:
        return True

    # common forms: "shutup toast", "shut up toast", "toast shut up", "toast, shut up"
    if "toast" in text and ("shutup" in text or "shut up" in text or "shut it" in text or "stfu" in text or "be quiet" in text or "shut the fuck up" in text):
        return True

    return False


def is_unmute_command(message: str) -> bool:
    """Detect the unmute command."""
    text = message.lower().strip()
    # Accept variants of request to resume talking
    return any(
        phrase in text
        for phrase in [
            "ok toast you can talk again",
            "ok toast you can talk",
            "toast you can talk again",
            "toast you can talk",
            "okay toast you can talk again",
            "okay toast you can talk",
            "toast talk again",
            "toast please talk again"
        ]
    )


def unmute_channel(channel_id: int) -> None:
    """Immediately unmute a channel/DM."""
    muted_threads.pop(channel_id, None)



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


def build_message_context(message: discord.Message) -> str:
    """Serialize a message into text for LLM context, including embeds."""
    text = (message.content or "").strip()
    embed_texts = []
    if getattr(message, "embeds", None):
        for idx, embed in enumerate(message.embeds, start=1):
            if embed.title:
                embed_texts.append(f"[embed#{idx} title: {embed.title}]")
            if embed.description:
                embed_texts.append(f"[embed#{idx} description: {embed.description}]")
    if embed_texts:
        if text:
            text += " " + " ".join(embed_texts)
        else:
            text = " ".join(embed_texts)
    return text or ""


async def handle_dm_response(message: discord.Message) -> None:
    """Handle AI responses to DM messages."""
    if message.author == bot.user:
        return

    if is_channel_muted(message.channel.id):
        return
    
    # Get conversation history
    key = get_conversation_key(message)
    history = conversation_history.get(key, "")
    
    # Get AI response
    error_details = None
    response = None
    try:
        response = await get_ai_response(history, message.content)
    except Exception as e:
        error_details = f"{type(e).__name__}: {str(e)}"
    
    # If AI fails (None response), DM the owner about the issue instead of sending to user
    if response is None:
        config = load_config("config")
        bot_config = config.get("bot_config", {})
        owner_id = bot_config.get("owner_user_id")
        
        if owner_id:
            try:
                owner = await bot.fetch_user(owner_id)
                error_msg = error_details if error_details else f"{AI_PROVIDER} returned None"
                await owner.send(f"⚠️ AI response failed for DM from {message.author} ({message.author.id}):\nMessage: {message.content}")
                await owner.send(f"**Error Details:**\n```\n{error_msg}\n```")
            except Exception as e:
                print(f"Failed to notify owner about AI error: {e}")
        
        error_msg = error_details if error_details else f"{AI_PROVIDER} returned None"
        print(f"AI response failed for DM from {message.author}: {error_msg}")
        return
    
    # If AI returned empty string, don't send anything
    if not response:
        return
    
    # Store conversation history and send response
    update_conversation_history(key, message.content, response)
    await message.channel.send(response)


async def should_respond_to_message(message: discord.Message) -> bool:
    """
    Use heuristics to decide if a message is interesting enough to respond to.
    Checks basic heuristics: mentions bot, is question, or is reply to bot.
    
    Args:
        message: The Discord message to evaluate
        
    Returns:
        True if the message meets the criteria to respond to, False otherwise
    """
    message_lower = message.content.lower()
    
    # Basic heuristics
    heuristics = {
        "mentions_bot": "toast" in message_lower,
        "is_question": message_lower.strip().endswith("?"),
        "is_reply_to_bot": False
    }
    
    # Check if message is a reply to the bot
    if message.reference:
        try:
            replied_to = await message.channel.fetch_message(message.reference.message_id)
            heuristics["is_reply_to_bot"] = replied_to.author == bot.user
        except:
            pass
    
    # If any of the heuristics are met, respond
    return any(heuristics.values())


async def handle_random_channel_response(message: discord.Message) -> None:
    """Handle intelligent AI responses in whitelisted channels based on message relevance."""
    if message.author == bot.user:
        return

    if is_channel_muted(message.channel.id):
        return
    
    # Check if channel is blacklisted
    blacklist = load_channel_blacklist("config")
    blacklist_ids = {entry["id"] for entry in blacklist}
    if message.channel.id in blacklist_ids:
        # If blacklisted and mentions toast, inform user
        if "toast" in message.content.lower():
            try:
                await message.channel.send("🤐 I'm currently muted in this channel. Use `$toast` to unmute me!")
            except Exception:
                pass
        return

    channel_meta = next((entry for entry in blacklist if entry["id"] == message.channel.id), None)
    if channel_meta and channel_meta.get("nickname"):
        # Optional: you can use this nickname for logging or future behavior.
        channel_nickname = channel_meta["nickname"]
    else:
        channel_nickname = None

    # Ask LLM if this message is interesting
    if not await should_respond_to_message(message):
        return
    
    # Fetch recent message history (last 15 messages before this one)
    history_messages = []
    try:
        async for msg in message.channel.history(limit=15, before=message):
            history_messages.insert(0, msg)  # Insert at beginning to maintain order
    except:
        pass
    
    # Build context string from recent messages
    context = ""
    for msg in history_messages:
        context += f"{msg.author.display_name}: {build_message_context(msg)}\n"
    context += f"{message.author.display_name}: {build_message_context(message)}\n"
    
    history = context
    #print(history)
    
    # Get AI response
    error_details = None
    response = None
    try:
        response = await get_ai_response(history, message.content)
    except Exception as e:
        error_details = f"{type(e).__name__}: {str(e)}"
    
    # If AI fails (None response), DM the owner about the issue instead of spamming the channel
    if response is None:
        config = load_config("config")
        bot_config = config.get("bot_config", {})
        owner_id = bot_config.get("owner_user_id")
        
        if owner_id:
            try:
                owner = await bot.fetch_user(owner_id)
                error_msg = error_details if error_details else f"{AI_PROVIDER} returned None"
                await owner.send(f"⚠️ AI response failed for channel message from {message.author} ({message.author.id}) in {message.guild.name}:\nMessage: {message.content}")
                await owner.send(f"**Error Details:**\n```\n{error_msg}\n```")
            except Exception as e:
                print(f"Failed to notify owner about AI error: {e}")
        
        error_msg = error_details if error_details else f"{AI_PROVIDER} returned None"
        print(f"AI response failed for channel message: {error_msg}")
        return
    
    # If AI returned empty string, don't send anything
    if not response:
        return
    
    # Send response
    await message.channel.send(response)


def load_commands_from_config() -> None:
    """
    Load commands from config/commands.json and register them with the bot.
    Each command entry specifies a module path and function name to import.
    Tracks success/failure for boot notification.
    """
    global loaded_commands
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
            
            loaded_commands.append((name, True, None))
            print(f"✓ Loaded command: ${name}")
        except Exception as e:
            cmd_name = cmd_config.get('name', 'unknown')
            loaded_commands.append((cmd_name, False, str(e)))
            print(f"✗ Failed to load command {cmd_name}: {e}")


def load_schedules_from_config() -> None:
    """
    Load schedules from config/schedule.json and register them with the scheduler.
    Tracks success/failure for boot notification.
    """
    global loaded_schedules
    config = load_config("config")
    
    for schedule_config in config["schedules"]:
        try:
            name = schedule_config["name"]
            
            # Skip if already registered
            if schedule_registry.get_schedule(name):
                continue
            
            message = schedule_config["message"]
            channel_id = schedule_config["channel_id"]
            schedule_type = schedule_config["type"]
            time_str = schedule_config["time"]
            enabled = schedule_config.get("enabled", True)
            
            weekdays = schedule_config.get("weekdays")
            date = schedule_config.get("date")
            timezone = schedule_config.get("timezone")
            
            # Register with schedule registry
            schedule_registry.register(
                name=name,
                message=message,
                channel_id=channel_id,
                schedule_type=schedule_type,
                time_str=time_str,
                weekdays=weekdays,
                date=date,
                enabled=enabled,
                timezone=timezone,
                months=schedule_config.get("months"),
                every_other_day=schedule_config.get("every_other_day", False)
            )
            
            loaded_schedules.append((name, True, None))
            status = "✓" if enabled else "⊘"
            print(f"{status} Loaded schedule: {name}")
        except Exception as e:
            schedule_name = schedule_config.get('name', 'unknown')
            loaded_schedules.append((schedule_name, False, str(e)))
            print(f"✗ Failed to load schedule {schedule_name}: {e}")


def register_commands_with_bot() -> None:
    """
    Register all commands from the registry with the Discord bot.
    Creates bot commands dynamically from the registry.
    """
    for cmd_config in command_registry.get_all_commands():
        name = cmd_config["name"]
        callback = cmd_config["callback"]
        
        # Create a command and add it to the bot
        cmd = commands.Command(callback, name=name)
        bot.add_command(cmd)
    
    # Debug: print registered commands
    print(f"✓ Registered {len(bot.commands)} commands with bot")
    for cmd in bot.commands:
        print(f"  - {cmd.name}")


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
    
    # Send boot notification DM to owner with detailed command/schedule info
    config = load_config("config")
    bot_config = config.get("bot_config", {})
    if bot_config.get("notify_on_boot", False):
        owner_id = bot_config.get("owner_user_id")
        if owner_id:
            try:
                owner = await bot.fetch_user(owner_id)
                
                # Build boot notification message
                boot_msg = "🍞 **Toast Boot Report**\n\n"
                
                # Commands section
                boot_msg += "**Commands:**\n"
                for cmd_name, success, error in loaded_commands:
                    if success:
                        boot_msg += f"✓ Loaded command: ${cmd_name}\n"
                    else:
                        boot_msg += f"✗ Failed to load command ${cmd_name}: {error}\n"
                
                boot_msg += "\n**Schedules:**\n"
                for sched_name, success, error in loaded_schedules:
                    if success:
                        boot_msg += f"✓ Loaded schedule: {sched_name}\n"
                    else:
                        boot_msg += f"✗ Failed to load schedule {sched_name}: {error}\n"
                
                await owner.send(boot_msg)
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
        await ctx.send(f"❌ An error occurred.")
        
        # Send follow-up message with error details
        error_details = f"**Error Details:**\n```\n{type(error).__name__}: {str(error)}\n```"
        try:
            await ctx.send(error_details)
        except Exception as e:
            # If the error message is too long, send a truncated version
            truncated = error_details[:2000]
            await ctx.send(truncated)
        
        print(f"Command error: {error}")


@bot.event
async def on_message(message: discord.Message) -> None:
    """Handle all messages for AI responses."""
    # Skip if message is from bot
    if message.author == bot.user:
        return

    # Skip messages that look like prices ($ followed by digit)
    if message.content.startswith('$') and len(message.content) > 1 and message.content[1].isdigit():
        return

    # Process commands first
    await bot.process_commands(message)

    # If msg requests silence, mute thread and skip responding
    if is_shutup_command(message.content) and not is_channel_muted(message.channel.id):
        mute_channel(message.channel.id)
        try:
            await message.channel.send("🤐 Got it. I’ll stay quiet here for 3 hours.")
        except Exception:
            pass
        return

    # If msg requests unmute, unmute thread and allow future responses
    if is_unmute_command(message.content) and is_channel_muted(message.channel.id):
        unmute_channel(message.channel.id)
        try:
            await message.channel.send("✅ Thanks! I’m back and ready to chat.")
        except Exception:
            pass
        return

    # If this is a command invocation (starts with the command prefix), do not trigger LLM responses
    if message.content.startswith('$'):
        return

    # If current thread is muted, ignore
    if is_channel_muted(message.channel.id):
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


if __name__ == "__main__":
    # Initialize and run bot
    initialize_bot()
    TOKEN = load_token("config")
    bot.run(TOKEN)
