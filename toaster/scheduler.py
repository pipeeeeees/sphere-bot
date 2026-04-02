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
        schedule_type: Union[str, Literal["weekly", "date"]],
        time_str: str,
        weekdays: Optional[List[int]] = None,
        date: Optional[str] = None,
        enabled: bool = True
    ) -> None:
        """
        Register a new scheduled message.
        
        Args:
            name: Unique name for the schedule
            message: Message content to send
            channel_id: Discord channel ID
            schedule_type: "weekly" or "date"
            time_str: Time in HH:MM format
            weekdays: List of weekdays [1-7] for weekly schedules
            date: YYYY-MM-DD for date-based schedules
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
        if schedule_type not in ["weekly", "date"]:
            raise ValueError("schedule_type must be 'weekly' or 'date'")
        
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
        
        self.schedules.append({
            "name": name,
            "message": message,
            "channel_id": channel_id,
            "type": schedule_type,
            "time": time_str,
            "weekdays": weekdays or [],
            "date": date,
            "enabled": enabled,
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
    
    async def start_scheduler(self, bot) -> None:
        """
        Start the scheduler background task.
        
        Args:
            bot: Discord bot instance
        """
        self.is_running = True
        
        while self.is_running:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_weekday = now.isoweekday()  # 1=Monday, 7=Sunday
            current_date = now.strftime("%Y-%m-%d")
            
            for schedule in self.schedules:
                if not schedule["enabled"]:
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
                
                # Send message if conditions are met
                if should_send:
                    try:
                        channel = bot.get_channel(schedule["channel_id"])
                        if channel:
                            await channel.send(schedule["message"])
                            schedule["last_sent"] = current_time
                    except Exception as e:
                        print(f"Error sending scheduled message '{schedule['name']}': {e}")
            
            # Check every 10 seconds to catch all minute boundaries
            await asyncio.sleep(10)
    
    def stop_scheduler(self) -> None:
        """Stop the scheduler background task."""
        self.is_running = False
