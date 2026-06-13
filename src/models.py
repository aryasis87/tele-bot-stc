"""
Data models untuk bot Telegram Admin.
Mirrors struktur data dari backend NestJS + frontend.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

# Zona waktu tampilan WIB (UTC+7). Waktu DB tetap UTC; ini hanya untuk display.
_WIB = timezone(timedelta(hours=7))


def _fmt_wib(iso_str: str, fmt: str = "%d %b %Y %H:%M") -> str:
    """ISO string (UTC/timestamptz) → string WIB + ' WIB'."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_WIB).strftime(fmt) + " WIB"

# ============================================================
# CURRENCY MAPPING (dipakai di seluruh modul)
# ============================================================
ISO_TO_UNIT: dict[str, str] = {
    # Selaras dengan ISO_TO_UNIT backend (profile.service.ts) & frontend (userProfileApi.ts)
    "IDR": "Rp", "USD": "$", "EUR": "€", "GBP": "£", "BRL": "R$",
    "COP": "Col$", "MXN": "MX$", "ARS": "AR$", "PEN": "S/", "CLP": "CL$",
    "NGN": "₦", "KES": "KSh", "GHS": "GH₵", "ZAR": "R",
    "INR": "₹", "PKR": "₨", "BDT": "৳", "LKR": "Rs",
    "PHP": "₱", "VND": "₫", "THB": "฿", "MYR": "RM", "SGD": "S$",
    "TRY": "₺", "UAH": "₴", "KZT": "₸", "UZS": "so'm",
    "RUB": "₽", "AMD": "֏", "AZN": "₼", "GEL": "₾",
    "EGP": "E£", "MAD": "MAD", "TND": "DT", "DZD": "DA",
    "SAR": "﷼", "AED": "AED", "KWD": "KD", "QAR": "QR", "OMR": "OMR",
    "HKD": "HK$", "TWD": "NT$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$",
    "VES": "Bs.S", "BOB": "Bs.", "PYG": "₲", "UYU": "$U", "GTQ": "Q",
    "HNL": "L", "CRC": "₡", "DOP": "RD$", "CUP": "$", "NIO": "C$",
}


@dataclass
class UserSession:
    """Mirrors: tabel 'sessions' di Supabase."""
    user_id: str
    email: str
    password: str  # PK di database
    stockity_token: str
    device_id: str
    device_type: str = "web"
    user_agent: str = ""
    user_timezone: str = "Asia/Bangkok"
    currency: str = "IDR"
    currency_iso: str = "IDR"
    logged_out_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.logged_out_at is None

    @property
    def display_currency(self) -> str:
        """Return simbol mata uang yang readable."""
        return ISO_TO_UNIT.get(self.currency, self.currency)


@dataclass
class WhitelistUser:
    """Mirrors: tabel 'whitelist_users' di Supabase."""
    id: Optional[str] = None
    email: str = ""
    name: Optional[str] = None
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    is_active: bool = True
    added_at: Optional[str] = None
    added_by: str = "system"
    last_login: Optional[str] = None
    is_primary: bool = False
    fcm_token: Optional[str] = None

    @property
    def added_at_formatted(self) -> str:
        if not self.added_at:
            return "-"
        try:
            return _fmt_wib(self.added_at)
        except:
            return self.added_at

    @property
    def last_login_formatted(self) -> str:
        if not self.last_login:
            return "Belum pernah"
        try:
            return _fmt_wib(self.last_login)
        except:
            return self.last_login

    @property
    def status_emoji(self) -> str:
        return "🟢" if self.is_active else "🔴"


@dataclass
class AdminUser:
    """Mirrors: tabel 'admin_users' di Supabase."""
    id: Optional[str] = None
    email: str = ""
    name: Optional[str] = None
    role: str = "admin"  # admin | super_admin
    is_active: bool = True
    created_at: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"


@dataclass
class BotAdmin:
    """Admin yang terdaftar di bot Telegram (tabel bot_admins)."""
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "admin"  # admin | super_admin
    is_active: bool = True
    created_at: Optional[str] = None
    created_by: Optional[int] = None

    @property
    def display_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(p for p in parts if p)
        if self.username:
            name += f" (@{self.username})"
        return name or f"User {self.chat_id}"


@dataclass
class UserBalance:
    """Hasil dari Stockity API /bank/v1/read."""
    real_balance: float = 0
    demo_balance: float = 0
    currency: str = "IDR"

    @property
    def display_currency(self) -> str:
        return ISO_TO_UNIT.get(self.currency, self.currency)

    @property
    def real_balance_formatted(self) -> str:
        """Format balance dengan separator ribuan."""
        return f"{self.display_currency} {self.real_balance:,.2f}"

    @property
    def demo_balance_formatted(self) -> str:
        return f"{self.display_currency} {self.demo_balance:,.2f}"


@dataclass
class DepositEvent:
    """Event deposit yang terdeteksi."""
    user_id: str
    email: str
    amount: float
    currency: str
    previous_balance: float
    new_balance: float
    detected_at: datetime = field(default_factory=datetime.utcnow)
    transaction_id: Optional[str] = None
    handler_name: Optional[str] = None

    @property
    def amount_formatted(self) -> str:
        unit = ISO_TO_UNIT.get(self.currency, self.currency)
        return f"{unit} {self.amount:,.2f}"


@dataclass
class UserProfile:
    """Profile user dari Stockity API."""
    id: int = 0
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    username: Optional[str] = None
    nickname: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    birthday: Optional[str] = None
    registered_at: Optional[str] = None
    avatar: Optional[str] = None
    currency: str = "IDR"
    email_verified: bool = False
    phone_verified: bool = False
    personal_data_locked: bool = False
    docs_verified: bool = False

    @property
    def full_name(self) -> str:
        name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return name or self.nickname or self.username or self.email

    @property
    def registered_at_formatted(self) -> str:
        if not self.registered_at:
            return "-"
        try:
            return _fmt_wib(self.registered_at)
        except:
            return self.registered_at


@dataclass
class UserStatistics:
    """Statistik user untuk /stats command."""
    total: int = 0
    active: int = 0
    inactive: int = 0
    recent_24h: int = 0  # Login dalam 24 jam terakhir
    recent_added_24h: int = 0  # Ditambahkan dalam 24 jam terakhir


@dataclass
class NotificationEvent:
    """Event untuk notifikasi real-time."""
    event_type: str  # new_user, deposit, login, dll
    title: str
    message: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)