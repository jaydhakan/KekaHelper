import ctypes
import logging
import os
import subprocess
from sys import platform
from time import sleep

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


logger = get_logger(__name__)


def get_env_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
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
