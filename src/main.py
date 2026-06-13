"""
Main Entry Point - Telegram Admin Bot
"""

import asyncio
import signal
import sys

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from config import TELEGRAM_BOT_TOKEN, BOT_MODE, WEBHOOK_URL, WEBHOOK_PORT, logger
from database import db
from notifications import NotificationService
from handlers import (
    # Core
    cmd_start, cmd_help, cmd_ping, cmd_myid,
    # Admin management
    cmd_admins, cmd_addadmin, cmd_removeadmin, cmd_toggleadmin,
    # User management
    cmd_users, cmd_user, cmd_search, cmd_aktifkan, cmd_nonaktifkan,
    # Balance & Deposit
    cmd_saldo, cmd_saldobyemail, cmd_depositlog, cmd_depositlog7, cmd_allsaldo, cmd_deposit,
    # Withdraw
    cmd_penarikan, cmd_penarikanlog, cmd_penarikanlog7,
    # Statistics
    cmd_stats, cmd_cekstatus,
    # Communication
    cmd_broadcast,
    # Callback & Error
    callback_handler, error_handler,
)


class TelegramAdminBot:
    """Main bot class."""

    def __init__(self):
        self.application: Application | None = None
        self.notification_service: NotificationService | None = None
        self._shutdown_event = asyncio.Event()

    def _register_handlers(self):
        """Register semua command handlers."""
        handlers = [
            # Core commands
            CommandHandler("start", cmd_start),
            CommandHandler("help", cmd_help),
            CommandHandler("ping", cmd_ping),
            CommandHandler("myid", cmd_myid),

            # Admin management
            CommandHandler("admins", cmd_admins),
            CommandHandler("addadmin", cmd_addadmin),
            CommandHandler("removeadmin", cmd_removeadmin),
            CommandHandler("toggleadmin", cmd_toggleadmin),

            # User management
            CommandHandler("users", cmd_users),
            CommandHandler("user", cmd_user),
            CommandHandler("search", cmd_search),
            CommandHandler("aktifkan", cmd_aktifkan),
            CommandHandler("aktifkan_user", cmd_aktifkan),
            CommandHandler("nonaktifkan", cmd_nonaktifkan),
            CommandHandler("nonaktifkan_user", cmd_nonaktifkan),

            # Balance & Deposit
            CommandHandler("saldo", cmd_saldo),
            CommandHandler("saldobyemail", cmd_saldobyemail),
            CommandHandler("deposit", cmd_deposit),
            CommandHandler("depositlog", cmd_depositlog),
            CommandHandler("depositlog7", cmd_depositlog7),
            CommandHandler("allsaldo", cmd_allsaldo),

            # Withdraw / Penarikan
            CommandHandler("penarikan", cmd_penarikan),
            CommandHandler("penarikanlog", cmd_penarikanlog),
            CommandHandler("penarikanlog7", cmd_penarikanlog7),

            # Statistics
            CommandHandler("stats", cmd_stats),
            CommandHandler("cekstatus", cmd_cekstatus),

            # Communication
            CommandHandler("broadcast", cmd_broadcast),

            # Callback query
            CallbackQueryHandler(callback_handler),
        ]

        for handler in handlers:
            self.application.add_handler(handler)

        # Error handler
        self.application.add_error_handler(error_handler)

    async def _setup_notifications(self):
        """Setup notification service dengan callbacks."""
        bot = self.application.bot
        self.notification_service = NotificationService(bot)

        # Register callbacks
        self.notification_service.on_deposit(self._on_deposit)
        self.notification_service.on_new_user(self._on_new_user)
        self.notification_service.on_login(self._on_login)

        # Start services
        await self.notification_service.start()

        logger.info("Notification service setup complete")

    async def _on_deposit(self, event):
        """Callback saat deposit terdeteksi."""
        await self.notification_service.send_deposit_notification(event)

    async def _on_new_user(self, event):
        """Callback saat user baru terdeteksi."""
        await self.notification_service.send_new_user_notification(event)

    async def _on_login(self, user):
        """Callback saat user login (last_login berubah)."""
        await self.notification_service.send_login_notification(user.user_id, user.email)

    async def _post_init(self, application: Application):
        """Hook yang dipanggil setelah bot diinisialisasi."""
        logger.info("Bot post_init - setting up notifications...")
        await self._setup_notifications()

    async def _shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down bot...")
        if self.notification_service:
            await self.notification_service.stop()
        self._shutdown_event.set()

    def _signal_handler(self, sig, frame):
        """Handle OS signals."""
        logger.info("Received signal %s, shutting down...", sig)
        asyncio.create_task(self._shutdown())

    async def run(self):
        """Main entry point."""
        logger.info("=" * 60)
        logger.info("TELEGRAM ADMIN BOT - Starting up")
        logger.info("=" * 60)

        # Build application
        self.application = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .post_init(self._post_init)
            .build()
        )

        # Register handlers
        self._register_handlers()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Run bot
        if BOT_MODE == "webhook" and WEBHOOK_URL:
            logger.info("Running in WEBHOOK mode on port %d", WEBHOOK_PORT)
            await self.application.initialize()
            await self.application.start()

            await self.application.updater.start_webhook(
                listen="0.0.0.0",
                port=WEBHOOK_PORT,
                url_path=TELEGRAM_BOT_TOKEN,
                webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
            )

            logger.info("Webhook listening on port %d", WEBHOOK_PORT)
            await self._shutdown_event.wait()

            await self.application.updater.stop_webhook()
            await self.application.stop()
            await self.application.shutdown()

        else:
            logger.info("Running in POLLING mode")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)

            logger.info("Bot is running! Press Ctrl+C to stop.")
            await self._shutdown_event.wait()

            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        logger.info("Bot stopped.")


def main():
    """Synchronous entry point."""
    bot = TelegramAdminBot()

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()