import ctypes
import logging
import os
import subprocess
from calendar import monthrange
from datetime import datetime, timedelta
from sys import platform
from time import sleep

from keka_helper.config import as_int, get_env

if not logging.getLogger().handlers:
    _level = logging.getLevelName(os.getenv("LOG_LEVEL", "INFO").upper())
    if not isinstance(_level, int):
        _level = logging.INFO
    logging.basicConfig(
        level=_level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


logger = get_logger(__name__)


def get_env_int(name: str, default: int, minimum: int = 1) -> int:
    value = get_env(name, str(default))
    try:
        parsed = as_int(value, default)
        if parsed < minimum:
            raise ValueError
        return parsed
    except ValueError:
        logger.warning(f"Invalid {name}={value!r}, using default={default}")
        return default


def notify_user(title: str, message: str, pause_seconds: float = 1.0) -> None:
    if platform == "linux":
        subprocess.run(["notify-send", title, message], check=False)
    elif platform == "win32":
        # noinspection PyUnresolvedReferences
        ctypes.windll.user32.MessageBoxW(0, message, title, 1)
    logger.info(f"{title}: {message}")
    if pause_seconds > 0:
        sleep(pause_seconds)


def format_timedelta(value: timedelta) -> str:
    total_minutes = int(abs(value.total_seconds()) // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes}m"


def parse_hhmm_text(value: str) -> timedelta:
    if not value:
        return timedelta(0)
    if ":" in value:
        try:
            hours, minutes = value.split(":", maxsplit=1)
            return timedelta(hours=int(hours), minutes=int(minutes))
        except ValueError:
            logger.warning(f"Invalid HH:MM value: {value}")
            return timedelta(0)
    hours = 0
    minutes = 0
    for part in value.split():
        if part.endswith("h"):
            hours = int(part[:-1])
        elif part.endswith("m"):
            minutes = int(part[:-1])
    return timedelta(hours=hours, minutes=minutes)


def remaining_weekdays_in_month(today: datetime) -> int:
    last_day = monthrange(today.year, today.month)[1]
    count = 0
    for day in range(today.day, last_day + 1):
        if datetime(today.year, today.month, day).weekday() < 5:
            count += 1
    return count


def convert_str_to_datetime(time_str: str) -> datetime:
    normalized = time_str.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(time_str[:19], fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported timestamp format: {time_str}")
