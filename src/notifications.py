"""
Notification System
- Real-time listeners via Supabase Realtime
- Deposit detection via balance polling
- Notification dispatcher ke Telegram
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Callable, Coroutine

from telegram import Bot
from telegram.constants import ParseMode

from config import (
    NOTIFICATION_CHANNEL_ID, DEPOSIT_CHECK_INTERVAL, logger,
    now_wib, naive_utc_to_wib,
)
from database import db
from stockity_api import StockityAPI, StockityAPIError
from models import DepositEvent, NotificationEvent, UserBalance


class NotificationService:
    """Service untuk mengelola semua notifikasi bot."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._deposit_callbacks: List[Callable[[DepositEvent], Coroutine]] = []
        self._user_callbacks: List[Callable[[NotificationEvent], Coroutine]] = []

    # ============================================================
    # CALLBACK REGISTRATION
    # ============================================================

    def on_deposit(self, callback: Callable[[DepositEvent], Coroutine]):
        """Register callback untuk event deposit."""
        self._deposit_callbacks.append(callback)

    def on_new_user(self, callback: Callable[[NotificationEvent], Coroutine]):
        """Register callback untuk event user baru."""
        self._user_callbacks.append(callback)

    # ============================================================
    # LIFECYCLE
    # ============================================================

    async def start(self):
        """Mulai semua notification services."""
        self._running = True
        logger.info("Starting NotificationService...")

        # Task 1: Deposit detection (polling)
        task_deposit = asyncio.create_task(
            self._deposit_detection_loop(),
            name="deposit_detection"
        )
        self._tasks.append(task_deposit)

        # Task 2: Realtime subscription untuk whitelist_users
        task_whitelist = asyncio.create_task(
            self._whitelist_realtime_loop(),
            name="whitelist_realtime"
        )
        self._tasks.append(task_whitelist)

        logger.info("NotificationService started with %d tasks", len(self._tasks))

    async def stop(self):
        """Hentikan semua notification services."""
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("NotificationService stopped")

    # ============================================================
    # DEPOSIT DETECTION (Transaction ID Tracking)
    # ============================================================

    async def _deposit_detection_loop(self):
        """
        Loop untuk mendeteksi deposit baru menggunakan endpoint transactions.
        Lebih reliable daripada balance comparison karena:
        - Berbasis transaction_id unik, bukan selisih saldo
        - Tidak terkena noise dari profit/loss trading
        Interval: DEPOSIT_CHECK_INTERVAL detik (default 5 menit).
        """
        logger.info(
            "Deposit detection loop started (interval=%ds, via transactions endpoint)",
            DEPOSIT_CHECK_INTERVAL,
        )

        # Catat waktu bot mulai — hanya deposit SETELAH ini yang di-notify
        # (mencegah spam notifikasi untuk deposit lama saat restart)
        self._bot_started_at: float = datetime.utcnow().timestamp()

        # Pre-populate seen transaction IDs dari semua yang sudah pernah disimpan di DB
        # agar tidak insert ulang saat restart
        self._seen_txn_ids: set = set()
        try:
            existing = await db.get_recent_deposits(hours=24 * 365 * 2)  # 2 tahun
            for dep in existing:
                if getattr(dep, "transaction_id", None):
                    self._seen_txn_ids.add(dep.transaction_id)
            logger.info(
                "Pre-populated %d known transaction IDs from DB",
                len(self._seen_txn_ids),
            )
        except Exception as e:
            logger.warning("Could not pre-populate txn IDs: %s", e)

        # Tunggu sebentar saat startup agar service lain siap
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._check_all_deposits()
            except Exception as e:
                logger.error("Error in deposit detection loop: %s", e)

            for _ in range(DEPOSIT_CHECK_INTERVAL):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def _check_all_deposits(self):
        """
        Cek deposit baru untuk SEMUA user aktif via transactions endpoint.

        Dijalankan CONCURRENT (semaphore 5, pola sama /allsaldo) supaya satu
        siklus selesai cepat meski ratusan user — syarat agar interval 1 menit
        benar-benar realtime. Versi lama memproses berurutan + sleep 0.5s/user
        sehingga 1 siklus bisa >>1 menit dan deposit telat terdeteksi.
        """
        sessions = await db.list_sessions(active_only=True, limit=1000)
        logger.debug("Checking deposits for %d active sessions", len(sessions))

        semaphore = asyncio.Semaphore(5)

        async def _guarded(session):
            async with semaphore:
                try:
                    await self._check_single_deposit(session)
                except Exception as e:
                    logger.warning(
                        "Failed to check deposits for %s: %s", session.user_id, e
                    )

        await asyncio.gather(*[_guarded(s) for s in sessions], return_exceptions=True)

    async def _check_single_deposit(self, session):
        """
        Cek deposit baru untuk satu user.
        Mengambil transactions endpoint lalu filter by transaction_id yang belum pernah dilihat.

        Logika dua tahap:
        - SIMPAN ke DB: semua deposit yang belum pernah dilihat (agar /depositlog terisi)
        - NOTIFY Telegram: hanya deposit yang terjadi SETELAH bot start
          (mencegah banjir notifikasi untuk deposit lama saat restart)
        """
        # Deteksi cukup halaman terbaru (max_pages=1): deposit baru selalu muncul
        # paling atas → hemat request untuk siklus tiap 1 menit.
        try:
            transactions = await StockityAPI.get_deposit_transactions_by_session(
                session, max_pages=1
            )
        except StockityAPIError:
            return

        for txn in transactions:
            txn_id = txn.get("transaction_id", "")
            if not txn_id:
                continue

            # Skip kalau sudah pernah diproses
            if txn_id in self._seen_txn_ids:
                continue

            # Mark as seen sekarang (sebelum proses) agar tidak double-process
            self._seen_txn_ids.add(txn_id)

            created_ts = txn.get("created_at", 0) or txn.get("processed_at", 0)
            amount     = txn.get("amount", 0)
            currency   = txn.get("currency", session.currency or "IDR")
            detected   = (
                datetime.utcfromtimestamp(created_ts)
                if created_ts else datetime.utcnow()
            )

            event = DepositEvent(
                user_id=session.user_id,
                email=session.email,
                amount=amount,
                currency=currency,
                previous_balance=0,
                new_balance=0,
                detected_at=detected,
                transaction_id=txn_id,
                handler_name=txn.get("handler_name", ""),
            )

            # Selalu simpan ke DB (untuk /depositlog dan /depositlog7)
            try:
                await db.save_deposit_event(event)
            except Exception as e:
                logger.warning("save_deposit_event error: %s", e)

            # Hanya kirim notifikasi untuk deposit yang terjadi SETELAH bot start
            is_new_deposit = (not created_ts) or (created_ts >= self._bot_started_at)
            if not is_new_deposit:
                logger.debug(
                    "Deposit %s (%s) terlalu lama — disimpan tapi tidak di-notify",
                    txn_id, detected.strftime("%d %b %Y"),
                )
                continue

            # Trigger callbacks (→ kirim Telegram notification)
            for callback in self._deposit_callbacks:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error("Deposit callback error: %s", e)

    # ============================================================
    # REALTIME: WHITELIST USERS
    # ============================================================

    async def _whitelist_realtime_loop(self):
        """
        Loop untuk listen perubahan pada tabel whitelist_users.
        Menggunakan polling karena Supabase Realtime Python support terbatas.
        """
        logger.info("Whitelist realtime loop started")

        # Track last known users untuk deteksi baru
        self._known_whitelist_ids: set = set()

        # Initial load
        initial_users = await db.list_whitelist_users(limit=1000)
        self._known_whitelist_ids = {u.id for u in initial_users if u.id}

        logger.info("Initial whitelist: %d users tracked", len(self._known_whitelist_ids))

        # Polling interval: 30 detik
        poll_interval = 30

        while self._running:
            try:
                await self._poll_whitelist_changes()
            except Exception as e:
                logger.error("Error in whitelist realtime loop: %s", e)

            for _ in range(poll_interval):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def _poll_whitelist_changes(self):
        """Poll whitelist users untuk deteksi user baru."""
        # Ambil user yang ditambahkan dalam 1 jam terakhir
        recent_users = await db.list_whitelist_users(limit=100)
        current_ids = {u.id for u in recent_users if u.id}

        # Deteksi user baru (ada di current tapi tidak di known)
        new_ids = current_ids - self._known_whitelist_ids

        for user in recent_users:
            if user.id in new_ids:
                # User baru terdeteksi!
                added_by = user.added_by or "system"
                is_self_register = added_by == "system"

                # NOTE: jangan masukkan kondisional ini ke dalam f-string multi-baris.
                # Newline di dalam f"..." (non-triple-quote) baru legal sejak Python 3.12
                # (PEP 701) → di Ubuntu 22.04/Python 3.10 jadi SyntaxError saat import.
                msg_text = (
                    "User baru telah mendaftar sendiri"
                    if is_self_register
                    else f"User baru ditambahkan oleh admin {added_by}"
                )
                event = NotificationEvent(
                    event_type="new_user",
                    title="User Baru Terdaftar",
                    message=msg_text,
                    user_id=user.user_id,
                    email=user.email,
                    metadata={
                        "name": user.name,
                        "added_by": added_by,
                        "is_self_register": is_self_register,
                        "added_at": user.added_at,
                    },
                )

                # Trigger callbacks
                for callback in self._user_callbacks:
                    try:
                        await callback(event)
                    except Exception as e:
                        logger.error("New user callback error: %s", e)

        # Update known set
        self._known_whitelist_ids = current_ids

    # ============================================================
    # DIRECT NOTIFICATIONS
    # ============================================================

    async def send_to_admins(self, message: str, parse_mode=ParseMode.HTML):
        """Kirim pesan ke semua admin bot."""
        admins = await db.list_bot_admins()
        for admin in admins:
            if admin.is_active:
                try:
                    await self.bot.send_message(
                        chat_id=admin.chat_id,
                        text=message,
                        parse_mode=parse_mode,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to send to admin %d: %s", admin.chat_id, e
                    )

    async def send_to_channel(self, message: str, parse_mode=ParseMode.HTML):
        """Kirim pesan ke notification channel jika dikonfigurasi."""
        if NOTIFICATION_CHANNEL_ID:
            try:
                await self.bot.send_message(
                    chat_id=NOTIFICATION_CHANNEL_ID,
                    text=message,
                    parse_mode=parse_mode,
                )
            except Exception as e:
                logger.warning("Failed to send to channel: %s", e)

    async def send_deposit_notification(self, event: DepositEvent):
        """Kirim notifikasi deposit ke semua admin."""
        txn_line     = f"\n🔑 <b>Txn ID:</b> <code>{event.transaction_id}</code>" if event.transaction_id else ""
        handler_line = f"\n💳 <b>Via:</b> {event.handler_name}" if event.handler_name else ""

        message = (
            f"💰 <b>DEPOSIT TERDETEKSI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> <code>{event.email}</code>\n"
            f"🆔 <b>ID:</b> <code>{event.user_id}</code>\n"
            f"💵 <b>Jumlah:</b> <code>{event.amount_formatted}</code>"
            f"{txn_line}"
            f"{handler_line}\n"
            f"🕐 <b>Waktu:</b> {naive_utc_to_wib(event.detected_at).strftime('%d %b %Y %H:%M:%S')} WIB\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        await self.send_to_admins(message)
        await self.send_to_channel(message)

    async def send_new_user_notification(self, event: NotificationEvent):
        """Kirim notifikasi user baru ke semua admin."""
        metadata = event.metadata or {}
        is_self = metadata.get("is_self_register", True)
        added_by = metadata.get("added_by", "system")

        message = (
            f"🆕 <b>USER BARU {'TERDAFTAR' if is_self else 'DITAMBAHKAN'}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📧 <b>Email:</b> <code>{event.email or '-'}</code>\n"
            f"🆔 <b>User ID:</b> <code>{event.user_id or '-'}</code>\n"
            f"👤 <b>Nama:</b> {metadata.get('name') or '-'}\n"
            f"🏷️ <b>Sumber:</b> {'Registrasi mandiri' if is_self else f'Ditambahkan oleh {added_by}'}\n"
            f"🕐 <b>Waktu:</b> {naive_utc_to_wib(event.created_at).strftime('%d %b %Y %H:%M:%S')} WIB\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        await self.send_to_admins(message)
        await self.send_to_channel(message)

    async def send_login_notification(self, user_id: str, email: str):
        """Kirim notifikasi user login."""
        message = (
            f"🔔 <b>USER LOGIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User <code>{email}</code> baru saja login\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🕐 Waktu: {now_wib().strftime('%d %b %Y %H:%M:%S')} WIB\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        await self.send_to_admins(message)


# Singleton akan diinisialisasi di main.py setelah bot dibuat
notification_service: Optional[NotificationService] = None