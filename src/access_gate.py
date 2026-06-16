"""
Gerbang password untuk bot (OPSIONAL).

Sumber password (prioritas):
  1. DB tabel `app_config`, key = 'bot_access_password'  → bisa diganti kapan saja
     lewat perintah /setpassword (tanpa restart) atau langsung di Supabase.
  2. Env ACCESS_PASSWORD  → nilai awal / fallback bila DB belum di-set.
  3. Kosong di keduanya  → gerbang NONAKTIF (bot publik, perilaku lama).

Status "sudah lolos" disimpan di memori proses (reset saat bot restart atau saat
password diganti). Tidak butuh perubahan skema DB (app_config sudah ada).
"""

import os
import time
import asyncio
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from config import logger, SUPER_ADMIN_CHAT_IDS
from database import db

# Nilai awal / fallback dari env.
ACCESS_PASSWORD: str = os.getenv("ACCESS_PASSWORD", "").strip()

# Key di tabel app_config tempat password disimpan.
_CONFIG_KEY = "bot_access_password"

# chat_id yang sudah lolos password (per sesi proses).
_unlocked_chats: set[int] = set()

# Cache password dari DB (hindari query tiap update).
_pw_cache: dict = {"value": None, "ts": 0.0}
_PW_TTL = 30.0  # detik


async def get_effective_password() -> str:
    """Ambil password aktif: DB (app_config) > env ACCESS_PASSWORD. Di-cache 30 dtk."""
    now = time.monotonic()
    if _pw_cache["value"] is not None and (now - _pw_cache["ts"]) < _PW_TTL:
        return _pw_cache["value"]

    pw = None
    try:
        res = await asyncio.to_thread(
            lambda: db.client.table("app_config").select("value")
            .eq("key", _CONFIG_KEY).limit(1).execute()
        )
        if res.data:
            v = res.data[0].get("value")
            if isinstance(v, str):
                pw = v
            elif isinstance(v, dict):
                pw = v.get("password")
    except Exception as e:
        logger.warning("get_effective_password error: %s", e)

    if not pw:
        pw = ACCESS_PASSWORD  # fallback env

    _pw_cache["value"] = pw or ""
    _pw_cache["ts"] = now
    return _pw_cache["value"]


async def set_password(new_password: str) -> bool:
    """Simpan password baru ke app_config. True jika berhasil."""
    try:
        await asyncio.to_thread(
            lambda: db.client.table("app_config").upsert(
                {
                    "key": _CONFIG_KEY,
                    "value": new_password,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="key",
            ).execute()
        )
        # Segarkan cache & paksa semua chat masukkan password baru.
        _pw_cache["value"] = new_password
        _pw_cache["ts"] = time.monotonic()
        return True
    except Exception as e:
        logger.error("set_password error: %s", e)
        return False


async def access_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Group=-1. Blokir update dari chat yang belum memasukkan password yang benar."""
    password = await get_effective_password()
    if not password:
        return  # gerbang nonaktif

    chat = update.effective_chat
    if chat is None:
        return
    chat_id = chat.id

    if chat_id in _unlocked_chats:
        return  # sudah lolos

    msg = update.effective_message
    text = (msg.text or "").strip() if msg is not None else ""

    if text == password:
        _unlocked_chats.add(chat_id)
        logger.info("Akses bot dibuka untuk chat %s (password benar)", chat_id)
        if msg is not None:
            await msg.reply_text("✅ Password benar. Akses dibuka.\nGunakan /start atau /help.")
        raise ApplicationHandlerStop

    if msg is not None:
        await msg.reply_text("🔒 Bot terkunci.\nMasukkan password untuk mengakses:")
    raise ApplicationHandlerStop


async def cmd_setpassword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setpassword <password_baru> — ganti password akses bot (tersimpan di DB).

    Otorisasi: kalau SUPER_ADMIN_CHAT_IDS di-set, hanya chat itu yang boleh.
    Kalau kosong, semua chat yang sudah lolos password boleh (gerbang sudah
    menyaring di group -1, jadi yang sampai sini pasti sudah tahu password lama).
    """
    chat_id = update.effective_chat.id if update.effective_chat else 0

    if SUPER_ADMIN_CHAT_IDS and chat_id not in SUPER_ADMIN_CHAT_IDS:
        await update.message.reply_text("⛔ Hanya owner yang boleh mengganti password.")
        return

    new_password = " ".join(context.args).strip() if context.args else ""
    if len(new_password) < 4:
        await update.message.reply_text(
            "Format: <code>/setpassword password_baru</code>\n"
            "(minimal 4 karakter)",
            parse_mode="HTML",
        )
        return

    if not await set_password(new_password):
        await update.message.reply_text("❌ Gagal menyimpan password. Coba lagi.")
        return

    # Paksa semua re-auth dengan password baru; setter tetap dibiarkan terbuka.
    _unlocked_chats.clear()
    _unlocked_chats.add(chat_id)

    logger.info("Password akses bot diganti oleh chat %s", chat_id)
    await update.message.reply_text(
        "✅ Password akses bot berhasil diganti dan langsung aktif.\n"
        "Semua user lain harus memasukkan password baru saat berinteraksi lagi."
    )
