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


def build_extra_hours_notification(
    working_days: int,
    total_effective: timedelta,
    office_time: timedelta,
) -> tuple[str, str]:
    required_total = office_time * working_days
    delta = total_effective - required_total
    avg = total_effective / working_days if working_days > 0 else timedelta(0)
    remaining_days = remaining_weekdays_in_month(datetime.now())

    if remaining_days > 0:
        office_minutes = int(office_time.total_seconds() // 60)
        delta_minutes = int(delta.total_seconds() // 60)
        required_per_day_minutes = office_minutes - round(delta_minutes / remaining_days)
        required_per_day_minutes = max(required_per_day_minutes, 7 * 60)
        h, m = divmod(required_per_day_minutes, 60)
        per_day_text = f"{h}h {m}m"
        if delta >= timedelta(0):
            daily_message = f"You can leave every day by doing {per_day_text}."
        else:
            daily_message = f"To reach average, do {per_day_text} every remaining working day."
    else:
        daily_message = "No remaining working days in this month."

    if delta >= timedelta(0):
        title = f"{format_timedelta(delta)} extra time this month"
    else:
        title = f"{format_timedelta(delta)} deficit this month"

    message = (
        f"{daily_message}\n"
        f"Days counted: {working_days} | Avg: {format_timedelta(avg)}"
    )
    return title, message


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
