"""
Toast Discord Bot - Entry Point
Scalable bot with modular command and scheduler systems.
"""

import discord
from discord.ext import commands
import asyncio
import importlib
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Union
import random
import time
from collections import deque

from toaster import CommandRegistry, ScheduleRegistry, load_token, get_gemini_response_with_key, get_grok_response_with_key
from toaster.config import load_config, load_channel_blacklist
from toaster.llm_agents.gemini import infer_if_reply_is_at_toast, load_gemini_key


# Create bot instance
bot = commands.Bot(command_prefix='$', intents=discord.Intents.all())

# Track bot start time for uptime command in shared state module
from toaster.state import set_start_time

# Conversation history storage
conversation_history = {}  # Dict[str, str] - user_id/channel_id -> history string

# Persistent person memory storage
PERSON_MEMORY_FILE = "config/person_memory.json"

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
        response, _ = get_gemini_response_with_key(history, message, "config")
        return response
    else:
        print(f"Unknown AI provider: {AI_PROVIDER}")
        return None


async def safe_send(channel, content: str) -> None:
    """Send `content` to `channel` robustly.

    - Splits content into Discord-safe chunks (<=2000 chars).
    - Prefers splitting on double-newlines, then newlines, then sentence boundaries.
    - Falls back to fixed-size slices if needed.
    """
    if not content:
        return

    MAX = 2000

    async def _send_piece(piece: str):
        try:
            await channel.send(piece)
        except Exception:
            # Last-resort: try smaller slices
            for i in range(0, len(piece), MAX - 10):
                try:
                    await channel.send(piece[i:i + (MAX - 10)])
                except Exception as e:
                    print(f"safe_send: failed to send slice: {e}")

    # If already small, try sending directly
    if len(content) <= MAX:
        try:
            await channel.send(content)
            return
        except Exception:
            # fall through to chunking logic
            pass

    # Try splitting by double newlines for readability
    parts = []
    for para in content.split('\n\n'):
        if not para:
            continue
        if len(para) <= MAX:
            parts.append(para)
        else:
            # split by single newline
            for line in para.split('\n'):
                if not line:
                    continue
                if len(line) <= MAX:
                    parts.append(line)
                else:
                    # try sentence-ish split
                    import re
                    sentences = re.split(r'(?<=[\.\!\?])\s+', line)
                    buf = ''
                    for sent in sentences:
                        if len(buf) + len(sent) + 1 <= MAX:
                            buf = (buf + ' ' + sent).strip()
                        else:
                            if buf:
                                parts.append(buf)
                            if len(sent) > MAX:
                                # final fallback: slice
                                for i in range(0, len(sent), MAX - 10):
                                    parts.append(sent[i:i + (MAX - 10)])
                                buf = ''
                            else:
                                buf = sent
                    if buf:
                        parts.append(buf)

    # Send each piece sequentially
    for piece in parts:
        await _send_piece(piece)
        await asyncio.sleep(0.1)


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
    if "toast" in text and ("shutup" in text or "shut up" in text or "shut it" in text or "stfu" in text or "be quiet" in text or "shut the fuck up" in text or "shut the hell up" in text):
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


def get_person_memory_path(config_dir: Union[str, Path] = "config") -> Path:
    """Return the path for the persistent person memory JSON file."""
    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)
    return config_path / "person_memory.json"


def load_person_memory(config_dir: Union[str, Path] = "config") -> dict:
    """Load the persisted memory database from disk."""
    memory_path = get_person_memory_path(config_dir)
    if not memory_path.exists():
        return {}
    try:
        with memory_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Failed to load person memory: {exc}")
        return {}


def save_person_memory(memory: dict, config_dir: Union[str, Path] = "config") -> None:
    """Persist person memory to disk."""
    memory_path = get_person_memory_path(config_dir)
    try:
        with memory_path.open("w", encoding="utf-8") as handle:
            json.dump(memory, handle, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Failed to save person memory: {exc}")


def extract_person_facts(text: str) -> list[str]:
    """Extract a few simple personal facts from a message body."""
    if not text:
        return []

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    clauses = [clause.strip() for clause in re.split(r"\s+and\s+", normalized, flags=re.IGNORECASE) if clause.strip()]
    patterns = [
        (r"\bi love\s+(.+)", lambda match: f"loves {match.group(1).strip()}"),
        (r"\bi like\s+(.+)", lambda match: f"likes {match.group(1).strip()}"),
        (r"\bi hate\s+(.+)", lambda match: f"hates {match.group(1).strip()}"),
        (r"\bi live in\s+(.+)", lambda match: f"lives in {match.group(1).strip()}"),
        (r"\bi work(?: at| in)?\s+(.+)", lambda match: f"works {match.group(1).strip()}"),
        (r"\bi play\s+(.+)", lambda match: f"plays {match.group(1).strip()}"),
        (r"\bi study\s+(.+)", lambda match: f"studies {match.group(1).strip()}"),
        (r"\bmy favorite (\w+)\s+is\s+(.+)", lambda match: f"favorite {match.group(1).strip()} is {match.group(2).strip()}"),
        (r"\bmy name is\s+(.+)", lambda match: f"name is {match.group(1).strip()}"),
        (r"\bi(?:'m| am)\s+(.+)", lambda match: f"is {match.group(1).strip()}"),
    ]

    facts = []
    for clause in clauses:
        for pattern, transform in patterns:
            match = re.search(pattern, clause, flags=re.IGNORECASE)
            if match:
                fact = re.sub(r"\s+", " ", transform(match)).strip(" .")
                if fact and fact.lower() not in {entry.lower() for entry in facts}:
                    facts.append(fact)
                break

    return facts


def update_person_memory(message: discord.Message, config_dir: Union[str, Path] = "config") -> dict:
    """Store lightweight facts about a person from their messages."""
    if not getattr(message.author, "id", None):
        return {}

    memory = load_person_memory(config_dir)
    user_key = f"user_{message.author.id}"
    entry = memory.get(user_key, {
        "user_id": message.author.id,
        "display_name": getattr(message.author, "display_name", None) or getattr(message.author, "name", None) or "",
        "channels": [],
        "facts": [],
        "message_count": 0,
        "last_seen": None,
    })

    display_name = getattr(message.author, "display_name", None) or getattr(message.author, "name", None) or entry.get("display_name", "")
    if display_name:
        entry["display_name"] = display_name

    channel_id = getattr(message.channel, "id", None)
    channel_name = getattr(message.channel, "name", None)
    if channel_id is not None:
        channels = entry.setdefault("channels", [])
        existing = next((channel for channel in channels if channel.get("id") == channel_id), None)
        if existing is None:
            channels.append({"id": channel_id, "name": channel_name})
        elif channel_name and existing.get("name") != channel_name:
            existing["name"] = channel_name

    text = build_message_context(message)
    new_facts = extract_person_facts(text)
    if new_facts:
        facts = entry.setdefault("facts", [])
        for fact in new_facts:
            if fact.lower() not in {existing_fact.lower() for existing_fact in facts}:
                facts.append(fact)
        if len(facts) > 12:
            entry["facts"] = facts[-12:]

    entry["message_count"] = entry.get("message_count", 0) + 1
    entry["last_seen"] = datetime.utcnow().isoformat()
    memory[user_key] = entry
    save_person_memory(memory, config_dir)
    return memory


def build_person_memory_context(message: discord.Message, config_dir: Union[str, Path] = "config") -> str:
    """Build a short memory snippet to attach to a reply prompt."""
    if not getattr(message.author, "id", None):
        return ""

    memory = load_person_memory(config_dir)
    user_key = f"user_{message.author.id}"
    entry = memory.get(user_key, {})
    facts = entry.get("facts", [])
    if not facts:
        return ""

    display_name = entry.get("display_name") or getattr(message.author, "display_name", None) or getattr(message.author, "name", None) or "this person"
    channel_names = [channel.get("name") for channel in entry.get("channels", []) if channel.get("name")]
    lines = [f"Known about {display_name} from earlier messages:"]
    for fact in facts[-5:]:
        lines.append(f"- {fact}")
    if channel_names:
        lines.append(f"Seen in: {', '.join(channel_names[-3:])}")
    return "\n".join(lines)


def format_history_line(prefix: str, content: str, timestamp: datetime | None = None) -> str:
    """Format a message line with a readable timestamp for LLM context."""
    if timestamp is None:
        timestamp = datetime.utcnow()
    stamp = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"[{stamp}] {prefix}: {content}".strip()


def update_conversation_history(key: str, user_message: str, ai_response: str) -> None:
    """Update conversation history for a user/channel."""
    global conversation_history
    
    # Initialize if not exists
    if key not in conversation_history:
        conversation_history[key] = ""
    
    # Add to history (keep last 10 exchanges to avoid token limits)
    history_lines = conversation_history[key].split('\n')
    timestamp = datetime.utcnow()
    new_lines = [format_history_line("User", user_message, timestamp), format_history_line("AI", ai_response, timestamp)]
    
    # Keep only last 10 exchanges (20 lines)
    combined_lines = history_lines + new_lines
    if len(combined_lines) > 20:
        combined_lines = combined_lines[-20:]
    
    conversation_history[key] = '\n'.join(combined_lines)


def build_message_context(message: discord.Message) -> str:
    """Serialize a message into text for LLM context, including embeds."""
    text = (message.content or "").strip()
    timestamp = getattr(message, "created_at", None)
    if timestamp is None:
        timestamp = datetime.utcnow()
    stamp = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    prefix = f"[{stamp}] {getattr(message.author, 'display_name', None) or getattr(message.author, 'name', None) or 'User'}"
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
    if text:
        return f"{prefix}: {text}"
    return prefix


async def handle_dm_response(message: discord.Message) -> None:
    """Handle AI responses to DM messages."""
    if message.author == bot.user:
        return

    if is_channel_muted(message.channel.id):
        return
    
    # Get conversation history
    key = get_conversation_key(message)
    history = conversation_history.get(key, "")
    memory_context = build_person_memory_context(message, config_dir="config")
    if memory_context:
        history = f"{memory_context}\n\n{history}" if history else memory_context
    
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
    
    # Store conversation history and send response (truncate to Discord limit)
    update_conversation_history(key, message.content, response)
    # Ensure response fits within Discord's 2000 character limit
    if len(response) > 2000:
        response = response[:1997] + "..."
    await safe_send(message.channel, response)

# Track recent bot activity for rate limiting
recent_bot_posts: deque = deque(maxlen=50)

INVITATION_PHRASES = ["anyone know", "does anyone", "what does everyone", "thoughts?", "any ideas"]
RECOMMENDATION_WORDS = ["recommend", "suggest", "should i", "worth it", "any good", "best way"]
HOT_TAKE_PHRASES = ["unpopular opinion", "hot take", "fight me", "change my mind", "controversial"]
FUN_TOPICS = ["movie", "game", "music", "anime", "food", "python", "ai"]  # customize for your server
QUESTION_STARTERS = ("who ", "what ", "where ", "when ", "why ", "how ", "can someone", "is there", "does anyone")
GREETINGS = ("hey", "hi ", "hello", "yo ", "sup", "howdy")

REAL_LIFE_ACTIVITY_WORDS = [
    "get food", "grab food", "get lunch", "grab lunch", "get dinner", "grab dinner",
    "get drinks", "grab drinks", "get coffee", "grab coffee",
    "hang out", "hang tonight", "come over", "meet up", "meetup",
    "go out", "going out", "come through", "pull up",
    "who's down", "whos down", "who wants to", "anyone down",
    "anyone want to", "anyone wanna", "who's in", "whos in",
    "irl", "in person", "in real life",
]

REAL_LIFE_VENUES = [
    "restaurant", "bar", "club", "party", "concert", "show",
    "the mall", "the gym", "the park", "the movies", "the game",
]

def is_real_life_plan(message_lower: str) -> bool:
    has_activity = any(phrase in message_lower for phrase in REAL_LIFE_ACTIVITY_WORDS)
    has_venue = any(place in message_lower for place in REAL_LIFE_VENUES)
    return has_activity or has_venue

async def should_respond_to_message(message: discord.Message) -> bool:
    message_lower = message.content.lower().strip()
    now = time.time()

    # Hard veto — never butt into real life plans
    if is_real_life_plan(message_lower):
        return False

    # --- Rate limiting: don't respond if bot spoke very recently ---
    recent_in_channel = [t for t in recent_bot_posts if t["channel"] == message.channel.id and now - t["time"] < 30]
    if len(recent_in_channel) >= 2:
        # Still allow direct mentions to break through
        if "toast" not in message_lower:
            return False

    heuristics = {
        # Original
        "mentions_bot": "toast" in message_lower,
        #"is_question": message_lower.endswith("?"),
        "is_reply_to_bot": False,

        # Better question detection
        #"implicit_question": message_lower.startswith(QUESTION_STARTERS),
        #"seeking_recommendation": any(w in message_lower for w in RECOMMENDATION_WORDS),

        # Social triggers
        "direct_address": message_lower.startswith("toast"),
        #"open_invitation": any(p in message_lower for p in INVITATION_PHRASES),
        #"hot_take_bait": any(p in message_lower for p in HOT_TAKE_PHRASES),
        #"greeting": any(message_lower.startswith(g) for g in GREETINGS) and len(message_lower) < 50,

        # Topic interest
        #"fun_topic": any(t in message_lower for t in FUN_TOPICS) and len(message.content) > 40,

        # Personality: small random chance for longer messages
        "random_chime_in": len(message.content) > 80 and random.random() < 0.02,

        # Deliberating between options
        "tossup_question": message_lower.count(" or ") >= 1 and message_lower.endswith("?"),
    }

    # Check reply-to-bot (your original logic)
    if message.reference:
        try:
            replied_to = await message.channel.fetch_message(message.reference.message_id)
            heuristics["is_reply_to_bot"] = replied_to.author == bot.user
        except:
            pass

    if any(heuristics.values()):
        recent_bot_posts.append({"channel": message.channel.id, "time": now})
        return True

    return False


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
        context += f"{build_message_context(msg)}\n"
    context += f"{build_message_context(message)}\n"

    memory_context = build_person_memory_context(message, config_dir="config")
    if memory_context:
        context = f"{memory_context}\n\n{context}" if context else memory_context
    history = context

    # Ask LLM if this message is interesting using Gemini inference helper.
    api_key = load_gemini_key("config")
    api_key = None # turn off relevant inference for now. its annoying
    if api_key:
        try:
            if not await infer_if_reply_is_at_toast(history, message.content, api_key):
                return
        except Exception as e:
            error_msg = f"Error inferring reply-worthy message: {e}"
            config = load_config("config")
            bot_config = config.get("bot_config", {})
            owner_id = bot_config.get("owner_user_id")
            if owner_id:
                try:
                    owner = await bot.fetch_user(owner_id)
                    await owner.send(f"⚠️ Gemini inference failed for channel {message.channel.id} in {message.guild.name}:")
                    await owner.send("**Error Details:**\n```\n" + error_msg + "\n```")
                except Exception as dm_err:
                    print(f"Failed to notify owner about inference error: {dm_err}")
            if not await should_respond_to_message(message):
                return
    else:
        if not await should_respond_to_message(message):
            return
    try:
        async for msg in message.channel.history(limit=15, before=message):
            history_messages.insert(0, msg)  # Insert at beginning to maintain order
    except:
        pass
    
    # Build context string from recent messages
    context = ""
    for msg in history_messages:
        context += f"{build_message_context(msg)}\n"
    context += f"{build_message_context(message)}\n"
    
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
    
    # Send response (robustly)
    if len(response) > 2000:
        # Let safe_send handle splitting nicely
        pass
    await safe_send(message.channel, response)


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
                every_other_day=schedule_config.get("every_other_day", False),
                allow_reboot=schedule_config.get("allow_reboot", False)
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
        update_person_memory(message, config_dir="config")

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
