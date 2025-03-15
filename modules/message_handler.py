import json
import io
import discord
import logging
import datetime
import random
import asyncio
import subprocess
import sys
import traceback

from modules import pollen
from modules import weather
from modules import report
from modules import subscriptions
from modules import google_gemini as gg

logger = logging.getLogger(__name__)
start_time = datetime.datetime.now()

SCHEDULE_FILE = "config/schedule.json"

def read_json(path):
    """Reads a JSON file and returns its contents."""
    try:
        with open(path, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error(f"Error reading {path}.")
        return {"reminders": []}

async def handle_message(bot, message, log_channel_id, GEMINI_API_KEY):
    """Handles messages for the bot"""
    try:
        # user DM handling - redirects to me
        if message.guild == None:
            # if the message.author is from user 326676188057567232, ignore it
            if message.author.id == 326676188057567232:
                pass
            else:
                user = await bot.fetch_user(326676188057567232)
                if user:  # Ensure the user was fetched successfully
                    await user.send(f"📬 **{message.author}** sent a DM to Sphere:\n{message.content}")


        # Get last however many messages from the channel or DM
        message_history = []
        async for msg in message.channel.history(limit=15, oldest_first=False):
            message_history.insert(0, f"{msg.author}: {msg.content}")
        history_str = "\n".join(message_history)
        #logger.info(f"📜 Message History:\n{history_str}")
        #user = await bot.fetch_user(326676188057567232)
        #await user.send(history_str)

        # Introduction message for first DM
        if message.guild == None and len(message_history) == 1:
            intro_msg = "👋 Hello! I'm Sphere, an Atlanta-based bot assistant. " \
                        "I give reports you can subscribe to. I am also pretty chill. Feel free to chat with me about anything. " \
                        "Type `$info` to see available subscription options or feel free to ask me anything!" \
                        "\n\n📝 **Note:** I am still in development, so please be patient with me. " \
                        "My source code is here: https://github.com/pipeeeeees/sphere-bot"
            await message.channel.send(intro_msg)
            logger.info("✅ Sent introduction message to new DM user.")

        # -- COMMANDS --
        # if $sub is sent, send the message sharing what the subscription options are
        if message.content.strip() == "$info":
            info_str = "👋 Hello! I'm Sphere, an Atlanta-based bot assistant.\n"
            info_str += "Here are the available commands I can respond to:\n"
            info_str += "  - `$sub' - Subscription options\n"
            info_str += "  - `$pollen` - Pollen count\n"
            info_str += "  - `$pollen plot` - Pollen count plot\n"
            #info_str += "  - `$pollen plot YYYY-MM-DD YYYY-MM-DD`
            info_str += "  - `$temp ascii` - ASCII temperature plot\n"
            info_str += "  - `$report` - A weather report\n"
            info_str += "  - `$uptime` - time since bot was last updated\n"
            info_str += "I also reply to DM's with an LLM. So feel free to chat!"
            await message.channel.send(info_str)
            logger.info("✅ Sent info message.")

        
        elif message.content.strip() == "$sub":
            subscribe_str = "📬 Here are the current Subscription Options:\n"
            #subscribe_str += "  - $sub weather\n"
            subscribe_str += "- $sub pollen\n"
            subscribe_str += "- $sub morning report\n"
            #subscribe_str += "  - $sub all\n"
            await message.channel.send(subscribe_str)
            logger.info("✅ Sent subscription options.")

        # if $sub pollen is sent, add the user to the pollen subscription list
        elif message.content.strip() == "$sub pollen":
            action = subscriptions.manage_pollen_subscription(message.author.id)
            if action == "added":
                await message.channel.send("📬 **You have been added to the pollen subscription list.**\n\nSend `$sub pollen` again to unsubscribe.")
            else:
                await message.channel.send("📬 **You have been removed from the pollen subscription list.**\n\nSend `$sub pollen` again to resubscribe.")
            logger.info(f"✅ {action.capitalize()} user {message.author.id} to pollen subscription list.")

        # if $sub morning report is sent, add the user to the morning report subscription list
        elif message.content.strip() == "$sub morning report":
            action = subscriptions.manage_morning_report_subscription(message.author.id)
            if action == "added":
                await message.channel.send("📬 **You have been added to the morning report subscription list.**\n\nSend `$sub morning report` again to unsubscribe.")
            else:
                await message.channel.send("📬 **You have been removed from the morning report subscription list.**\n\nSend `$sub morning report` again to resubscribe.")
            logger.info(f"✅ {action.capitalize()} user {message.author.id} to morning report subscription list.")

        # if $schedule is sent in the bot-testing channel, send the schedule file
        elif message.content.strip() == "$schedule" and int(message.channel.id) == int(log_channel_id):
            schedule_data = read_json(SCHEDULE_FILE)
            schedule_text = json.dumps(schedule_data, indent=4)

            file = discord.File(io.BytesIO(schedule_text.encode()), filename="schedule.json")
            await message.channel.send("📂 **Schedule file:**", file=file)
            logger.info("✅ Sent schedule file.")

        # if $uptime is sent, send the uptime
        elif message.content.strip() == "$uptime":
            current_time = datetime.datetime.now()
            uptime_seconds = (current_time - start_time).total_seconds()

            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)

            uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"
            
            await message.channel.send(f"⏳ Uptime: **{uptime_str}**")
            logger.info(f"✅ Sent uptime: {uptime_str}")

        # if $pollen is sent, send the pollen count
        elif "$pollen" in message.content.strip():
            parts = message.content.strip().split()
            if len(parts) == 1:
                pollen_count = pollen.get_atl_pollen_count_by_date(datetime.date.today().strftime("%Y/%m/%d"))
                if isinstance(pollen_count, int):
                    await message.channel.send(f"🌼 **Pollen count:** {pollen_count}")
                elif pollen_count is None:
                    await message.channel.send("❌ **Pollen count not reported.**")
                else:
                    await message.channel.send("❌ **HTML Parsing Error.**")
            elif len(parts) == 2 and parts[1] == "plot":
                # start_date is first of the current year
                start_date = datetime.date(datetime.date.today().year, 1, 1).strftime("%Y-%m-%d")
                end_date = datetime.date.today().strftime("%Y-%m-%d")
                await pollen.plot_pollen_counts(start_date, end_date)
                await message.channel.send(file=discord.File("plots/plot.png"))
            elif len(parts) == 4 and parts[1] == "plot":
                try:
                    start_date = parts[2]
                    end_date = parts[3]
                    start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")

                    if start_dt > end_dt:
                        await message.channel.send("❌ **Start date must be before end date.**")
                        return
                    
                    await pollen.plot_pollen_counts(start_date, end_date)
                    await message.channel.send(file=discord.File("plots/plot.png"))
                except ValueError:
                    await message.channel.send("❌ **Invalid date format. Use YYYY-MM-DD YYYY-MM-DD.**")


        # if $temp ascii is sent, send the ascii plot
        elif message.content.strip() == "$temp ascii":
            ascii_plot = weather.get_hourly_temperatures_ascii_plot()
            await message.channel.send(ascii_plot)  # Send as a raw string, not inside {}
            logger.info("✅ Sent ASCII temp plot.")


        # if $report is sent, send the morning report
        elif message.content.strip() == "$report":
            report_str = report.get_morning_report()
            await message.channel.send(report_str)
            alert_str = report.get_weather_alerts()
            if alert_str is not None:
                await message.channel.send(alert_str)
            else:
                await message.channel.send("❌ **No weather alerts.**")
            logger.info("✅ Sent morning report.")

        # if $reboot is sent, reboot
        elif message.content.strip() == "$reboot":
            subprocess.Popen([sys.executable, "main.py"])  # Start new bot process
            sys.exit(0)  # Exit the current script

        # if $pull is sent, git pull
        elif message.content.strip() == "$pull":
            try:
                process = subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
                output = process.stdout + process.stderr
                await message.channel.send(f"📝 Git Pull Output:\n```\n{output}\n```")
            except subprocess.CalledProcessError as e:
                await message.channel.send(f"❌ Git pull failed:\n```\n{e.output}\n```")
                print(f"Git pull failed: {e}")


        # if a Trae Young tweet is detected, send a message
        elif "https://fixvx.com/TheTraeYoung/status/" in message.content:
            # a 1 in 3 chance to send a message
            result = random.randint(1, 100)
            if result < 40:
                await message.channel.send("🗣️🗣️🗣️ **Trae Young Tweeted** 🗣️🗣️🗣️")
                logger.info("✅ Sent The Trae Young message.")
            #elif result == 2:
            #    # wait for 10 seconds
            #    await asyncio.sleep(10)
            #    await message.channel.send("Fuck Trae Young")
            #    logger.info("✅ Sent The Trae Young message.")

        # default case handler
        else:
            # If the message is a DM, process the full message
            if isinstance(message.channel, discord.DMChannel):
                raw_message = message.content
                await message.channel.send(gg.get_gemini_response(history_str, raw_message, GEMINI_API_KEY))
            # If the message is in a server channel, require @Sphere mention
            elif f"<@1275637004821860402>" in message.content:
                # Remove the mention from the message before processing
                raw_message = message.content.replace(f"<@1275637004821860402>", "").strip()
                await message.channel.send(gg.get_gemini_response(history_str, raw_message, GEMINI_API_KEY))
            else:
                return  # Ignore messages without @Sphere in a server channel
            
    except Exception as e:
        error_message = f"⚠️ Error encountered:\n{traceback.format_exc()}"
        user = await bot.fetch_user(326676188057567232)
        if user:
            await user.send(f"🚨 Error while processing command: `{message.content}`\n{error_message}")
        logger.error(error_message)