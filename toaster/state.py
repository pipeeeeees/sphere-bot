"""
Bot state container to avoid circular dependencies in command modules.
"""

from datetime import datetime
from typing import Optional

start_time: Optional[datetime] = None


def set_start_time(value: datetime) -> None:
    global start_time
    start_time = value


def get_start_time() -> Optional[datetime]:
    return start_time
