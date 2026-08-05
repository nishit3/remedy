from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".remedy"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_key() -> str | None:
    if not CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("anthropic_api_key")


def save_key(key: str) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"anthropic_api_key": key}), encoding="utf-8")


def clear_key() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({}), encoding="utf-8")
