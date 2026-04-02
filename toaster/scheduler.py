"""
Scheduler System
Manages recurring message schedules based on day of week, specific dates, and times.
"""

from typing import Dict, List, Any, Optional, Union
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
from datetime import datetime, time
import asyncio

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # zoneinfo not available in older Python versions


class ScheduleRegistry:
    """
    Registry for managing scheduled messages.
    
    Schedule entries are dictionaries with:
    - name: unique name for the schedule
    - message: message content to send
    - channel_id: Discord channel ID to send to
    - type: "weekly" or "date"
    - time: time to send (HH:MM format)
    - weekdays: [1-7] for weekly (1=Monday, 7=Sunday)
    - date: YYYY-MM-DD for specific dates
    - enabled: boolean to enable/disable the schedule
    """
    
    def __init__(self):
        self.schedules: List[Dict[str, Any]] = []
        self.is_running = False
    
    def register(
        self,
        name: str,
        message: str,
        channel_id: int,
        schedule_type: Union[str, Literal["weekly", "date", "annual"]],
        time_str: str,
        weekdays: Optional[List[int]] = None,
        date: Optional[str] = None,
        enabled: bool = True,
        timezone: Optional[str] = None,
        months: Optional[List[int]] = None,
        every_other_day: bool = False
    ) -> None:
        """
        Register a new scheduled message.
        
        Args:
            name: Unique name for the schedule
            message: Message content to send
            channel_id: Discord channel ID
            schedule_type: "weekly", "date", or "annual"
            time_str: Time in HH:MM format
            weekdays: List of weekdays [1-7] for weekly schedules
            date: YYYY-MM-DD for date-based schedules
            months: Optional list of months [1-12] when message can be sent
            every_other_day: If True, only send on alternating day-of-month in the months window
            enabled: Whether the schedule is active
        """
        if self.get_schedule(name):
            raise ValueError(f"Schedule '{name}' already registered")
        
        # Validate time format
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            raise ValueError(f"Invalid time format '{time_str}', use HH:MM")
        
        # Validate schedule type
        if schedule_type not in ["weekly", "date", "annual"]:
            raise ValueError("schedule_type must be 'weekly', 'date', or 'annual'")
        
        # Validate months filter
        if months is not None:
            if not months or not all(1 <= m <= 12 for m in months):
                raise ValueError("months must contain values 1-12")

        # Validate based on type
        if schedule_type == "weekly":
            if not weekdays or not all(1 <= d <= 7 for d in weekdays):
                raise ValueError("weekdays must contain values 1-7 for weekly schedules")
        elif schedule_type == "date":
            if not date:
                raise ValueError("date required for date-based schedules")
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format '{date}', use YYYY-MM-DD")
        elif schedule_type == "annual":
            if not date:
                raise ValueError("date required for annual schedules (e.g., 2000-01-01 or 2027-01-01)")
            try:
                annual_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format '{date}', use YYYY-MM-DD")
            # Normalize month/day for annual check
            date = annual_date.strftime("%m-%d")
        else:
            raise ValueError("schedule_type must be 'weekly', 'date', or 'annual'")

        # Validate timezone
        if timezone is not None:
            if ZoneInfo is None:
                raise ValueError("Timezone support is unavailable: install Python 3.9+ or required backport")
            try:
                ZoneInfo(timezone)
            except Exception:
                raise ValueError(f"Invalid timezone '{timezone}'. Use IANA zone name, e.g. 'America/New_York'.")

        self.schedules.append({
            "name": name,
            "message": message,
            "channel_id": channel_id,
            "type": schedule_type,
            "time": time_str,
            "weekdays": weekdays or [],
            "date": date,
            "months": months or [],
            "every_other_day": every_other_day,
            "enabled": enabled,
            "timezone": timezone,
            "last_sent": None  # Track last sent time to avoid duplicates
        })
    
    def get_schedule(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a schedule by name.
        
        Args:
            name: Schedule name
            
        Returns:
            Schedule dictionary or None if not found
        """
        for schedule in self.schedules:
            if schedule["name"] == name:
                return schedule
        return None
    
    def get_all_schedules(self) -> List[Dict[str, Any]]:
        """
        Get all registered schedules.
        
        Returns:
            List of schedule dictionaries
        """
        return [s.copy() for s in self.schedules]
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a schedule.
        
        Args:
            name: Schedule name
            
        Returns:
            True if schedule was removed, False if not found
        """
        for i, schedule in enumerate(self.schedules):
            if schedule["name"] == name:
                self.schedules.pop(i)
                return True
        return False
    
    def toggle_schedule(self, name: str, enabled: bool) -> bool:
        """
        Enable or disable a schedule.
        
        Args:
            name: Schedule name
            enabled: True to enable, False to disable
            
        Returns:
            True if successful, False if schedule not found
        """
        schedule = self.get_schedule(name)
        if schedule:
            schedule["enabled"] = enabled
            return True
        return False
    
    class ScheduleContext:
        """Minimal context for running command handlers from scheduler."""

        def __init__(self, channel, bot):
            self.channel = channel
            self.bot = bot

        async def send(self, message: str):
            return await self.channel.send(message)

    async def _execute_scheduled_command(self, command_text: str, channel, bot):
        """Execute command-like scheduled message using commands_impl functions."""
        if not command_text.startswith('$'):
            await channel.send(command_text)
            return

        from toaster.commands_impl import mlb_all_standings_command, mlb_division_standings_command

        content = command_text.strip()
        parts = content[1:].split()
        if not parts:
            await channel.send(command_text)
            return

        cmd = parts[0].lower()
        args = parts[1:]

        ctx = self.ScheduleContext(channel, bot)

        owner_id = 326676188057567232

        try:
            if cmd == 'mlb_standings':
                await mlb_all_standings_command(ctx)
            elif cmd == 'mlb_division' and args:
                await mlb_division_standings_command(ctx, ' '.join(args))
            else:
                # Unknown scheduled command; do not echo raw command text
                return
        except Exception as e:
            # DM owner with execution errors and do not send direct channel message
            print(f"Error executing scheduled command '{command_text}': {e}")
            try:
                owner = await bot.fetch_user(owner_id)
                if owner:
                    await owner.send(f"⚠️ Scheduled command failed: '{command_text}' in channel {channel.id}: {e}")
            except Exception as dm_err:
                print(f"Failed to notify owner about scheduled command error: {dm_err}")

    async def start_scheduler(self, bot) -> None:
        """
        Start the scheduler background task.
        
        Args:
            bot: Discord bot instance
        """
        self.is_running = True
        
        while self.is_running:
            for schedule in self.schedules:
                if not schedule["enabled"]:
                    continue

                schedule_tz = schedule.get("timezone")
                if schedule_tz and ZoneInfo is not None:
                    try:
                        schedule_now = datetime.now(ZoneInfo(schedule_tz))
                    except Exception as e:
                        print(f"Invalid timezone for schedule '{schedule['name']}': {e}")
                        continue
                else:
                    schedule_now = datetime.now()

                current_time = schedule_now.strftime("%H:%M")
                current_weekday = schedule_now.isoweekday()  # 1=Monday, 7=Sunday
                current_date = schedule_now.strftime("%Y-%m-%d")
                current_month = schedule_now.month

                # Skip if schedule has reduced month window
                if schedule.get("months"):
                    if current_month not in schedule["months"]:
                        continue

                # Alternating-day filter for schedules that require every-other-day frequency
                if schedule.get("every_other_day"):
                    if schedule_now.day % 2 == 0:
                        continue

                # Skip if already sent in this minute
                if schedule["last_sent"] == current_time:
                    continue

                should_send = False

                # Check weekly schedules
                if schedule["type"] == "weekly":
                    if current_weekday in schedule["weekdays"]:
                        if current_time == schedule["time"]:
                            should_send = True

                # Check date-based schedules
                elif schedule["type"] == "date":
                    if current_date == schedule["date"]:
                        if current_time == schedule["time"]:
                            should_send = True

                # Check annual schedules
                elif schedule["type"] == "annual":
                    current_month_day = schedule_now.strftime("%m-%d")
                    if current_month_day == schedule.get("date"):
                        if current_time == schedule["time"]:
                            should_send = True

                # Send message if conditions are met
                if should_send:
                    try:
                        channel = bot.get_channel(schedule["channel_id"])
                        if channel:
                            if isinstance(schedule["message"], str) and schedule["message"].startswith('$'):
                                await self._execute_scheduled_command(schedule["message"], channel, bot)
                            else:
                                await channel.send(schedule["message"])
                            schedule["last_sent"] = current_time
                    except Exception as e:
                        print(f"Error sending scheduled message '{schedule['name']}': {e}")

            # Check every 10 seconds to catch all minute boundaries
            await asyncio.sleep(10)

    def stop_scheduler(self) -> None:
        """Stop the scheduler background task."""
        self.is_running = False
