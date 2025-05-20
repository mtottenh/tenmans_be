import datetime
from typing import Optional

import pytz


def now_utc() -> datetime.datetime:
    """Get current UTC datetime with timezone information."""
    return datetime.datetime.now(datetime.timezone.utc)


def make_aware(dt: datetime.datetime) -> datetime.datetime:
    """Convert naive datetime to timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def format_datetime(dt: Optional[datetime.datetime]) -> Optional[str]:
    """Format datetime as ISO string with timezone."""
    if dt is None:
        return None
    aware_dt = make_aware(dt)
    return aware_dt.isoformat()


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime.datetime]:
    """Parse ISO format datetime string to timezone-aware datetime."""
    if dt_str is None:
        return None
    dt = datetime.datetime.fromisoformat(dt_str)
    return make_aware(dt)