import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str = field(repr=False)
    bot_token: str = field(repr=False)
    owner_id: int
    cipher: Fernet = field(repr=False)
    data: Path
    sync_interval: int = 1800
    miniapp_url: str | None = None

    @classmethod
    def load(cls):
        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env", interpolate=False)
        api_id = int(os.environ["TELEGRAM_API_ID"])
        owner_id = int(os.environ["TELEGRAM_OWNER_ID"])
        api_hash = os.environ["TELEGRAM_API_HASH"].strip()
        token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
        interval = int(os.environ.get("KILLER_SYNC_INTERVAL", "1800"))
        profile = os.environ.get("KILLER_PROFILE", "default")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", profile):
            raise ValueError("Invalid KILLER_PROFILE")
        data = root / "data"
        if profile != "default":
            data = data / profile
        miniapp_url = os.environ.get("KILLER_MINIAPP_URL", "").strip() or None
        if miniapp_url:
            parsed = urlsplit(miniapp_url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.query or parsed.fragment):
                raise ValueError("KILLER_MINIAPP_URL must be an HTTPS URL without credentials")
        if interval and interval < 300:
            raise ValueError("KILLER_SYNC_INTERVAL must be 0 or at least 300 seconds")
        if api_id <= 0 or owner_id <= 0 or len(api_hash) != 32 or ":" not in token:
            raise ValueError("تنظیمات تلگرام معتبر نیست.")
        return cls(api_id, api_hash, token, owner_id,
                   Fernet(os.environ["KILLER_SESSION_KEY"].encode()), data,
                   interval, miniapp_url)
