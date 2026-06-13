"""
Konfigurasi Bot Telegram Admin
Semua variabel lingkungan di-load dari .env
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load .env dari root project
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# ============================================================
# TELEGRAM
# ============================================================
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN wajib diisi di .env!")

# Super admin chat IDs (dipisah koma)
_SUPER_ADMIN_RAW: str = os.getenv("SUPER_ADMIN_CHAT_IDS", "")
SUPER_ADMIN_CHAT_IDS: list[int] = [
    int(x.strip()) for x in _SUPER_ADMIN_RAW.split(",") if x.strip().isdigit()
]

# Notifikasi channel/group ID
NOTIFICATION_CHANNEL_ID: int | None = None
_notif_ch = os.getenv("NOTIFICATION_CHANNEL_ID", "").strip()
if _notif_ch.lstrip("-").isdigit():
    NOTIFICATION_CHANNEL_ID = int(_notif_ch)

# ============================================================
# SUPABASE
# ============================================================
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL dan SUPABASE_SERVICE_KEY wajib diisi!")

# ============================================================
# STOCKITY API
# ============================================================
STOCKITY_API_URL: str = os.getenv("STOCKITY_API_URL", "https://api.stockity.id")

# ============================================================
# MODE OPERASI
# ============================================================
BOT_MODE: str = os.getenv("BOT_MODE", "polling")  # polling | webhook
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))

# ============================================================
# DEPOSIT DETECTION
# ============================================================
DEPOSIT_CHECK_INTERVAL: int = int(os.getenv("DEPOSIT_CHECK_INTERVAL", "60"))  # 1 menit (realtime)
MIN_DEPOSIT_AMOUNT: float = float(os.getenv("MIN_DEPOSIT_AMOUNT", "1"))

# ============================================================
# LOGGING
# ============================================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")

# Buat folder logs kalau belum ada
LOG_PATH = ROOT_DIR / LOG_FILE
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# DEFAULT HEADERS (mirrors backend NestJS)
# ============================================================
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
DEFAULT_TIMEZONE = "Asia/Bangkok"

# ============================================================
# ZONA WAKTU TAMPILAN — WIB (Asia/Jakarta, UTC+7, tanpa DST)
# ============================================================
# Dipakai HANYA untuk tampilan di pesan Telegram. Waktu internal/DB tetap UTC.
WIB = timezone(timedelta(hours=7))


def now_wib() -> datetime:
    """Waktu sekarang dalam WIB (tz-aware)."""
    return datetime.now(WIB)


def ts_to_wib(ts) -> datetime:
    """Unix timestamp (detik, UTC) → datetime WIB."""
    return datetime.fromtimestamp(ts, WIB)


def naive_utc_to_wib(dt: datetime) -> datetime:
    """datetime naive (dianggap UTC) → WIB."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB)


def iso_to_wib(s: str) -> datetime:
    """String ISO (UTC/timestamptz) → datetime WIB."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB)


def setup_logging() -> logging.Logger:
    """Setup logger dengan file handler dan stream handler."""
    logger = logging.getLogger("TelegramAdminBot")
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        # Format log
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Stream handler (console)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # File handler
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logging()