from __future__ import annotations

import json
import os
from pathlib import Path

import aiofiles

from backend.models.server import Settings

CONFIG_DIR = Path(os.path.expanduser("~/.config/noctalia-vpn"))
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


async def load_settings() -> Settings:
    ensure_dirs()
    if not SETTINGS_FILE.exists():
        return Settings()
    try:
        async with aiofiles.open(SETTINGS_FILE, "r") as f:
            raw = await f.read()
        data = json.loads(raw or "{}")
        return Settings.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return Settings()


async def save_settings(settings: Settings) -> None:
    ensure_dirs()
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    async with aiofiles.open(tmp, "w") as f:
        await f.write(json.dumps(settings.model_dump(exclude_none=True), indent=2))
    os.replace(tmp, SETTINGS_FILE)
