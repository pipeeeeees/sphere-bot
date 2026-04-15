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
from toaster.config import load_config, load_channel_whitelist


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


# AI Provider Configuration
# Options: "grok", "gemini"
AI_PROVIDER = "grok"


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
    response = await get_ai_response(history, message.content)
    
    # If AI fails, DM the owner about the issue instead of sending to user
    if not response:
        config = load_config("config")
        bot_config = config.get("bot_config", {})
        owner_id = bot_config.get("owner_user_id")
        
        if owner_id:
            try:
                owner = await bot.fetch_user(owner_id)
                await owner.send(f"⚠️ AI response failed for DM from {message.author} ({message.author.id}):\nMessage: {message.content}")
            except Exception as e:
                print(f"Failed to notify owner about AI error: {e}")
        
        print(f"AI response failed for DM from {message.author}: {AI_PROVIDER} returned None")
        return
    
    # Store conversation history and send response
    update_conversation_history(key, message.content, response)
    await message.channel.send(response)


async def should_respond_to_message(message: discord.Message) -> bool:
    """
    Use the LLM to intelligently decide if a message is interesting enough to respond to.
    Checks basic heuristics first, then asks the LLM for its judgment with conversation context.
    
    Args:
        message: The Discord message to evaluate
        
    Returns:
        True if the message is interesting enough to respond to, False otherwise
    """
    message_lower = message.content.lower()
    
    # Basic heuristics to pass to LLM for context
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
    
    # If none of the heuristics are met, don't bother asking the LLM
    if not any(heuristics.values()):
        return False
    
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
    
    # Ask the LLM if this message is interesting
    #print(context)
    prompt = f"""Decide if this Discord message thread is interesting enough to respond to. You are Toast in this conversation. Respond with ONLY "true" or "false" - nothing else.
- Does it mention the bot (Toast) in the last message? if so, respond with "true"
- Is the last message hint at an IRL question or gathering? If so, respond with "false". I don't want you to butt in on personal plans or real life arrangements.
- Is the overall conversation engaging? Can you add something funny or valuable to it? If so, respond with "true"

Recent conversation:
{context}
"""

    response = await get_ai_response("", prompt)
    
    if not response:
        return False
    
    # Parse the response to boolean
    return response.strip().lower() == "true"


async def handle_random_channel_response(message: discord.Message) -> None:
    """Handle intelligent AI responses in whitelisted channels based on message relevance."""
    if message.author == bot.user:
        return

    if is_channel_muted(message.channel.id):
        return
    
    # Check if channel is whitelisted
    whitelist = load_channel_whitelist("config")
    whitelist_ids = {entry["id"] for entry in whitelist}
    if message.channel.id not in whitelist_ids:
        return

    channel_meta = next((entry for entry in whitelist if entry["id"] == message.channel.id), None)
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
    response = await get_ai_response(history, message.content)
    
    # If AI fails, DM the owner about the issue instead of spamming the channel
    if not response:
        config = load_config("config")
        bot_config = config.get("bot_config", {})
        owner_id = bot_config.get("owner_user_id")
        
        if owner_id:
            try:
                owner = await bot.fetch_user(owner_id)
                await owner.send(f"⚠️ AI response failed for channel message from {message.author} ({message.author.id}) in {message.guild.name}:\nMessage: {message.content}")
            except Exception as e:
                print(f"Failed to notify owner about AI error: {e}")
        
        print(f"AI response failed for channel message: {AI_PROVIDER} returned None")
        return
    
    # Send response
    await message.channel.send(response)


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
                await owner.send("🍞 Toast has booted successfully!!")
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


# Initialize on module load so registries are populated for testing/imports
initialize_bot()


if __name__ == "__main__":
    # Re-initialize in case configuration changed, then run bot
    TOKEN = load_token("config")
    bot.run(TOKEN)
