"""
Supabase Database Client & Queries
Mirrors fungsionalitas dari backend NestJS + frontend.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from supabase import create_client, Client
from postgrest.exceptions import APIError

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, logger
from models import (
    UserSession, WhitelistUser, AdminUser, BotAdmin,
    UserBalance, UserProfile, UserStatistics, DepositEvent
)

# Serialize pembuatan id deposit_events (max+1) supaya tidak balapan antar task.
_deposit_id_lock = asyncio.Lock()


class SupabaseDB:
    """Singleton client untuk Supabase."""

    _instance: Optional["SupabaseDB"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self._initialized = True
        logger.info("SupabaseDB client initialized")

    # ============================================================
    # BOT ADMINS (tabel: bot_admins)
    # ============================================================

    async def get_bot_admin(self, chat_id: int) -> Optional[BotAdmin]:
        """Cek apakah chat_id adalah admin bot."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("bot_admins")
                .select("*")
                .eq("chat_id", chat_id)
                .limit(1)
                .execute()
            )
            if not result or not result.data:
                return None
            d = result.data[0]
            return BotAdmin(
                chat_id=d["chat_id"],
                username=d.get("username"),
                first_name=d.get("first_name"),
                last_name=d.get("last_name"),
                role=d.get("role", "admin"),
                is_active=d.get("is_active", True),
                created_at=d.get("created_at"),
                created_by=d.get("created_by"),
            )
        except Exception as e:
            logger.error(f"get_bot_admin error: {e}")
            return None

    async def is_bot_admin(self, chat_id: int) -> bool:
        """Cek apakah chat_id adalah admin bot yang aktif."""
        admin = await self.get_bot_admin(chat_id)
        return admin is not None and admin.is_active

    async def is_super_admin(self, chat_id: int) -> bool:
        """Cek apakah chat_id adalah super admin bot."""
        admin = await self.get_bot_admin(chat_id)
        return admin is not None and admin.is_active and admin.role == "super_admin"

    async def add_bot_admin(self, admin: BotAdmin) -> bool:
        """Tambahkan admin bot baru."""
        try:
            data = {
                "chat_id": admin.chat_id,
                "username": admin.username,
                "first_name": admin.first_name,
                "last_name": admin.last_name,
                "role": admin.role,
                "is_active": admin.is_active,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": admin.created_by,
            }
            await asyncio.to_thread(
                lambda: self.client.table("bot_admins").insert(data).execute()
            )
            logger.info(f"Bot admin ditambahkan: {admin.chat_id} ({admin.username})")
            return True
        except APIError as e:
            if "duplicate" in str(e).lower():
                logger.warning(f"Bot admin {admin.chat_id} sudah ada")
                return False
            logger.error(f"add_bot_admin error: {e}")
            raise

    async def remove_bot_admin(self, chat_id: int) -> bool:
        """Hapus admin bot."""
        try:
            await asyncio.to_thread(
                lambda: self.client.table("bot_admins")
                .delete()
                .eq("chat_id", chat_id)
                .execute()
            )
            logger.info(f"Bot admin dihapus: {chat_id}")
            return True
        except Exception as e:
            logger.error(f"remove_bot_admin error: {e}")
            return False

    async def toggle_bot_admin(self, chat_id: int, is_active: bool) -> bool:
        """Aktifkan/nonaktifkan admin bot."""
        try:
            await asyncio.to_thread(
                lambda: self.client.table("bot_admins")
                .update({"is_active": is_active})
                .eq("chat_id", chat_id)
                .execute()
            )
            return True
        except Exception as e:
            logger.error(f"toggle_bot_admin error: {e}")
            return False

    async def list_bot_admins(self) -> List[BotAdmin]:
        """Daftar semua admin bot."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("bot_admins")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return [
                BotAdmin(
                    chat_id=d["chat_id"],
                    username=d.get("username"),
                    first_name=d.get("first_name"),
                    last_name=d.get("last_name"),
                    role=d.get("role", "admin"),
                    is_active=d.get("is_active", True),
                    created_at=d.get("created_at"),
                    created_by=d.get("created_by"),
                )
                for d in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"list_bot_admins error: {e}")
            return []

    async def count_bot_admins(self) -> int:
        """Hitung jumlah admin bot."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("bot_admins")
                .select("*", count="exact", head=True)
                .execute()
            )
            return result.count or 0
        except Exception as e:
            logger.error(f"count_bot_admins error: {e}")
            return 0

    # ============================================================
    # SESSIONS (tabel: sessions)
    # ============================================================

    async def get_session(self, user_id: str) -> Optional[UserSession]:
        """Ambil session user by user_id."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("sessions")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if not result or not result.data:
                return None
            d = result.data[0]
            return UserSession(
                user_id=d["user_id"],
                email=d["email"],
                password=d.get("PK", ""),
                stockity_token=d.get("stockity_token", ""),
                device_id=d.get("device_id", ""),
                device_type=d.get("device_type", "web"),
                user_agent=d.get("user_agent", ""),
                user_timezone=d.get("user_timezone", "Asia/Bangkok"),
                currency=d.get("currency", "IDR"),
                currency_iso=d.get("currency_iso", "IDR"),
                logged_out_at=d.get("logged_out_at"),
                updated_at=d.get("updated_at"),
            )
        except Exception as e:
            logger.error(f"get_session error: {e}")
            return None

    async def get_session_by_email(self, email: str) -> Optional[UserSession]:
        """Ambil session user by email."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("sessions")
                .select("*")
                .eq("email", email.lower().strip())
                .limit(1)
                .execute()
            )
            if not result or not result.data:
                return None
            d = result.data[0]
            return UserSession(
                user_id=d["user_id"],
                email=d["email"],
                password=d.get("PK", ""),
                stockity_token=d.get("stockity_token", ""),
                device_id=d.get("device_id", ""),
                device_type=d.get("device_type", "web"),
                user_agent=d.get("user_agent", ""),
                user_timezone=d.get("user_timezone", "Asia/Bangkok"),
                currency=d.get("currency", "IDR"),
                currency_iso=d.get("currency_iso", "IDR"),
                logged_out_at=d.get("logged_out_at"),
                updated_at=d.get("updated_at"),
            )
        except Exception as e:
            logger.error(f"get_session_by_email error: {e}")
            return None

    async def list_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = False,
    ) -> List[UserSession]:
        """Daftar semua sessions."""
        try:
            query = self.client.table("sessions").select("*")
            if active_only:
                query = query.is_("logged_out_at", "null")
            query = query.order("updated_at", desc=True).limit(limit)
            if offset > 0:
                query = query.range(offset, offset + limit - 1)

            result = await asyncio.to_thread(lambda: query.execute())
            return [
                UserSession(
                    user_id=d["user_id"],
                    email=d["email"],
                    password=d.get("PK", ""),
                    stockity_token=d.get("stockity_token", ""),
                    device_id=d.get("device_id", ""),
                    device_type=d.get("device_type", "web"),
                    user_agent=d.get("user_agent", ""),
                    user_timezone=d.get("user_timezone", "Asia/Bangkok"),
                    currency=d.get("currency", "IDR"),
                    currency_iso=d.get("currency_iso", "IDR"),
                    logged_out_at=d.get("logged_out_at"),
                    updated_at=d.get("updated_at"),
                )
                for d in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"list_sessions error: {e}")
            return []

    async def count_sessions(self, active_only: bool = False) -> int:
        """Hitung jumlah sessions."""
        try:
            query = self.client.table("sessions").select("*", count="exact", head=True)
            if active_only:
                query = query.is_("logged_out_at", "null")
            result = await asyncio.to_thread(lambda: query.execute())
            return result.count or 0
        except Exception as e:
            logger.error(f"count_sessions error: {e}")
            return 0

    # ============================================================
    # WHITELIST USERS (tabel: whitelist_users)
    # ============================================================

    async def get_whitelist_user(self, email: str) -> Optional[WhitelistUser]:
        """Ambil whitelist user by email."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*")
                .eq("email", email.lower().strip())
                .limit(1)
                .execute()
            )
            if not result or not result.data:
                return None
            d = result.data[0]
            return WhitelistUser(
                id=d.get("id"),
                email=d["email"],
                name=d.get("name"),
                user_id=d.get("user_id"),
                device_id=d.get("device_id"),
                is_active=d.get("is_active", True),
                added_at=d.get("added_at"),
                added_by=d.get("added_by", "system"),
                last_login=d.get("last_login"),
                is_primary=d.get("is_primary", False),
                fcm_token=d.get("fcm_token"),
            )
        except Exception as e:
            logger.error(f"get_whitelist_user error: {e}")
            return None

    async def get_whitelist_user_by_id(self, user_id: str) -> Optional[WhitelistUser]:
        """Ambil whitelist user by user_id atau email."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if not result or not result.data:
                # Coba by email
                result = await asyncio.to_thread(
                    lambda: self.client.table("whitelist_users")
                    .select("*")
                    .eq("email", user_id.lower().strip())
                    .limit(1)
                    .execute()
                )
            if not result or not result.data:
                return None
            d = result.data[0]
            return WhitelistUser(
                id=d.get("id"),
                email=d["email"],
                name=d.get("name"),
                user_id=d.get("user_id"),
                device_id=d.get("device_id"),
                is_active=d.get("is_active", True),
                added_at=d.get("added_at"),
                added_by=d.get("added_by", "system"),
                last_login=d.get("last_login"),
                is_primary=d.get("is_primary", False),
                fcm_token=d.get("fcm_token"),
            )
        except Exception as e:
            logger.error(f"get_whitelist_user_by_id error: {e}")
            return None

    async def list_whitelist_users(
        self,
        limit: int = 100,
        offset: int = 0,
        active_only: bool = False,
        added_by: Optional[str] = None,
        is_primary: bool = False,
    ) -> List[WhitelistUser]:
        """Daftar whitelist users dengan filter."""
        try:
            query = self.client.table("whitelist_users").select("*")

            if active_only:
                query = query.eq("is_active", True)
            if added_by:
                query = query.eq("added_by", added_by)
            query = query.eq("is_primary", is_primary)

            query = query.order("added_at", desc=True).limit(limit)
            if offset > 0:
                query = query.range(offset, offset + limit - 1)

            result = await asyncio.to_thread(lambda: query.execute())
            return [
                WhitelistUser(
                    id=d.get("id"),
                    email=d["email"],
                    name=d.get("name"),
                    user_id=d.get("user_id"),
                    device_id=d.get("device_id"),
                    is_active=d.get("is_active", True),
                    added_at=d.get("added_at"),
                    added_by=d.get("added_by", "system"),
                    last_login=d.get("last_login"),
                    is_primary=d.get("is_primary", False),
                    fcm_token=d.get("fcm_token"),
                )
                for d in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"list_whitelist_users error: {e}")
            return []

    async def count_whitelist_users(
        self,
        active_only: bool = False,
        added_by: Optional[str] = None,
    ) -> int:
        """Hitung jumlah whitelist users."""
        try:
            query = self.client.table("whitelist_users").select("*", count="exact", head=True)
            if active_only:
                query = query.eq("is_active", True)
            if added_by:
                query = query.eq("added_by", added_by)
            result = await asyncio.to_thread(lambda: query.execute())
            return result.count or 0
        except Exception as e:
            logger.error(f"count_whitelist_users error: {e}")
            return 0

    async def toggle_whitelist_user(self, email: str, is_active: bool) -> bool:
        """Aktifkan/nonaktifkan whitelist user."""
        try:
            await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .update({"is_active": is_active})
                .eq("email", email.lower().strip())
                .execute()
            )
            return True
        except Exception as e:
            logger.error(f"toggle_whitelist_user error: {e}")
            return False

    # ============================================================
    # ADMIN USERS (tabel: admin_users)
    # ============================================================

    async def list_admin_users(self) -> List[AdminUser]:
        """Daftar admin users dari sistem (bukan bot admin)."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("admin_users")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return [
                AdminUser(
                    id=d.get("id"),
                    email=d["email"],
                    name=d.get("name"),
                    role=d.get("role", "admin"),
                    is_active=d.get("is_active", True),
                    created_at=d.get("created_at"),
                )
                for d in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"list_admin_users error: {e}")
            return []

    # ============================================================
    # DEPOSIT TRACKING (tabel: balance_history)
    # ============================================================

    async def get_last_balance(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Ambil balance terakhir yang tercatat untuk user."""
        try:
            result = await asyncio.to_thread(
                lambda: self.client.table("balance_history")
                .select("*")
                .eq("user_id", user_id)
                .order("checked_at", desc=True)
                .limit(1)
                .execute()
            )
            if not result or not result.data:
                return None
            return result.data[0]
        except Exception as e:
            logger.error(f"get_last_balance error: {e}")
            return None

    async def save_balance_snapshot(
        self, user_id: str, email: str, real_balance: float,
        demo_balance: float, currency: str
    ) -> bool:
        """Simpan snapshot balance untuk tracking deposit."""
        try:
            data = {
                "user_id": user_id,
                "email": email,
                "real_balance": real_balance,
                "demo_balance": demo_balance,
                "currency": currency,
                "checked_at": datetime.utcnow().isoformat(),
            }
            await asyncio.to_thread(
                lambda: self.client.table("balance_history").insert(data).execute()
            )
            return True
        except Exception as e:
            logger.error(f"save_balance_snapshot error: {e}")
            return False

    async def get_recent_deposits(self, hours: int = 24) -> List[DepositEvent]:
        """Ambil deposit yang terdeteksi dalam N jam terakhir."""
        try:
            since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            result = await asyncio.to_thread(
                lambda: self.client.table("deposit_events")
                .select("*")
                .gte("detected_at", since)
                .order("detected_at", desc=True)
                .limit(50)
                .execute()
            )
            return [
                DepositEvent(
                    user_id=d["user_id"],
                    email=d["email"],
                    amount=d["amount"],
                    currency=d.get("currency", "IDR"),
                    previous_balance=d.get("previous_balance", 0),
                    new_balance=d.get("new_balance", 0),
                    detected_at=datetime.fromisoformat(d["detected_at"].replace("Z", "+00:00")),
                    transaction_id=d.get("transaction_id"),
                )
                for d in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"get_recent_deposits error: {e}")
            return []

    async def save_deposit_event(self, event: DepositEvent) -> bool:
        """Simpan event deposit yang terdeteksi."""
        try:
            data = {
                "user_id": event.user_id,
                "email": event.email,
                "amount": event.amount,
                "currency": event.currency,
                "previous_balance": event.previous_balance,
                "new_balance": event.new_balance,
                "detected_at": event.detected_at.isoformat(),
                "transaction_id": event.transaction_id,
            }
            if event.transaction_id:
                # Dedup tanpa bergantung pada UNIQUE INDEX transaction_id (DB lama
                # tidak punya → upsert on_conflict gagal dgn 42P10). Cek dulu, lalu
                # insert kalau belum ada.
                existing = await asyncio.to_thread(
                    lambda: self.client.table("deposit_events")
                    .select("id").eq("transaction_id", event.transaction_id)
                    .limit(1).execute()
                )
                if existing.data:
                    return True  # sudah tersimpan → skip (anti-duplikat)

            # Generate `id` sendiri (max+1) agar TIDAK memakai sequence
            # deposit_events_id_seq — di DB lama service_role tak punya hak USAGE
            # pada sequence (error 42501). Di-serialize dengan lock (proses tunggal).
            async with _deposit_id_lock:
                res = await asyncio.to_thread(
                    lambda: self.client.table("deposit_events")
                    .select("id").order("id", desc=True).limit(1).execute()
                )
                data["id"] = ((res.data[0]["id"] if res.data else 0) or 0) + 1
                await asyncio.to_thread(
                    lambda: self.client.table("deposit_events").insert(data).execute()
                )
            return True
        except Exception as e:
            logger.error(f"save_deposit_event error: {e}")
            return False

    # ============================================================
    # STATISTICS
    # ============================================================

    async def get_user_statistics(self) -> UserStatistics:
        """Ambil statistik user (mirrors dari supabaseRepository.ts)."""
        try:
            threshold_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()

            # Total
            total_result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*", count="exact", head=True)
                .eq("is_primary", False)
                .execute()
            )
            total = total_result.count or 0

            # Active
            active_result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*", count="exact", head=True)
                .eq("is_primary", False)
                .eq("is_active", True)
                .execute()
            )
            active = active_result.count or 0

            # Inactive
            inactive_result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*", count="exact", head=True)
                .eq("is_primary", False)
                .eq("is_active", False)
                .execute()
            )
            inactive = inactive_result.count or 0

            # Recent login (24h)
            recent_result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*", count="exact", head=True)
                .eq("is_primary", False)
                .gte("last_login", threshold_24h)
                .execute()
            )
            recent = recent_result.count or 0

            # Recent added (24h)
            recent_added_result = await asyncio.to_thread(
                lambda: self.client.table("whitelist_users")
                .select("*", count="exact", head=True)
                .eq("is_primary", False)
                .eq("added_by", "system")
                .gte("added_at", threshold_24h)
                .execute()
            )
            recent_added = recent_added_result.count or 0

            return UserStatistics(
                total=total,
                active=active,
                inactive=inactive,
                recent_24h=recent,
                recent_added_24h=recent_added,
            )
        except Exception as e:
            logger.error(f"get_user_statistics error: {e}")
            return UserStatistics()

# Singleton instance
db = SupabaseDB()