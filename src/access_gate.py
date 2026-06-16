"""
Gerbang password untuk bot (OPSIONAL — diaktifkan lewat env ACCESS_PASSWORD).

Perilaku:
  - ACCESS_PASSWORD di-set  → bot terkunci. Setiap chat harus mengirim password
    yang benar dulu sebelum boleh memakai perintah apa pun. Setelah benar, chat
    "terbuka" dan bot beroperasi normal seperti biasa.
  - ACCESS_PASSWORD kosong   → gerbang nonaktif, bot tetap publik (perilaku lama).

Status "sudah lolos" disimpan di memori proses (reset saat bot restart → user
memasukkan password lagi). Tidak butuh perubahan skema DB.
"""

import os

from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from config import logger

ACCESS_PASSWORD: str = os.getenv("ACCESS_PASSWORD", "").strip()

# chat_id yang sudah lolos password (per sesi proses).
_unlocked_chats: set[int] = set()


async def access_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dipasang di handler group paling awal (group=-1). Memblokir semua update
    dari chat yang belum memasukkan password yang benar."""
    if not ACCESS_PASSWORD:
        return  # gerbang nonaktif → lanjut ke handler normal

    chat = update.effective_chat
    if chat is None:
        return
    chat_id = chat.id

    if chat_id in _unlocked_chats:
        return  # sudah lolos → biarkan handler normal berjalan

    msg = update.effective_message
    text = (msg.text or "").strip() if msg is not None else ""

    if text == ACCESS_PASSWORD:
        _unlocked_chats.add(chat_id)
        logger.info("Akses bot dibuka untuk chat %s (password benar)", chat_id)
        if msg is not None:
            await msg.reply_text(
                "✅ Password benar. Akses dibuka.\nGunakan /start atau /help."
            )
        # Jangan proses pesan password ini sebagai perintah lain.
        raise ApplicationHandlerStop

    # Belum lolos & password salah/kosong → minta password lalu blokir update.
    if msg is not None:
        await msg.reply_text("🔒 Bot terkunci.\nMasukkan password untuk mengakses:")
    raise ApplicationHandlerStop
