import os
from os import path
from typing import Dict, Optional

from dotenv import dotenv_values

_BASE_DIR = path.dirname(path.dirname(path.abspath(__file__)))
_ENV_PATH = path.join(_BASE_DIR, ".env")

if path.exists(_ENV_PATH):
    _RAW_ENV: Dict[str, str] = {
        k: v for k, v in dotenv_values(_ENV_PATH).items() if v is not None
    }
else:
    _RAW_ENV = dict(os.environ)


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    value = _RAW_ENV.get(key)
    if value is None or value == "":
        return default
    return value


def as_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"[CONFIG] Invalid int for value '{value}'") from exc
