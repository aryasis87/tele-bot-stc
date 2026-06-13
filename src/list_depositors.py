"""
Utilitas one-off: daftar email SEMUA user yang PERNAH deposit.

Mengambil LIVE dari Stockity (endpoint transactions) per user — sama seperti
/depositlog — bukan dari tabel deposit_events (yang hanya cache realtime).

Jalankan dari root bot:
    cd /opt/telegram-admin-bot
    sudo venv/bin/python src/list_depositors.py

Catatan: user yang token-nya sudah kedaluwarsa tidak bisa dicek (di-skip) —
mereka perlu login ulang agar terhitung. Hasil = pendeposit di antara sesi
yang token-nya masih valid.
"""
import asyncio

from database import db
from stockity_api import StockityAPI


async def main() -> None:
    sessions = await db.list_sessions(active_only=False, limit=100000)
    depositors: dict[str, int] = {}
    ok = 0
    fail = 0

    sem = asyncio.Semaphore(6)  # konkuren, pola sama /allsaldo

    async def check(s) -> None:
        nonlocal ok, fail
        async with sem:
            try:
                txns = await StockityAPI.get_deposit_transactions_by_session(s, max_pages=None)
                ok += 1
                if txns and getattr(s, "email", None):
                    depositors[s.email.strip().lower()] = len(txns)
            except Exception:
                fail += 1

    await asyncio.gather(*[check(s) for s in sessions])

    emails = sorted(e for e in depositors if e)
    print("\n===== EMAIL PENDEPOSIT (" + str(len(emails)) + ") =====")
    print(", ".join(emails))
    print(
        f"\n[sesi total={len(sessions)} | token valid={ok} | "
        f"token gagal/kedaluwarsa={fail}]"
    )


if __name__ == "__main__":
    asyncio.run(main())
