"""
Stockity API Client
Mirrors fungsionalitas dari backend NestJS (profile.service.ts).
Menggunakan curl binary untuk bypass Cloudflare (sama dengan backend).
"""

import asyncio
import json
import os
import shutil
import subprocess
from typing import Optional, Dict, Any, List

from config import STOCKITY_API_URL, DEFAULT_USER_AGENT, DEFAULT_TIMEZONE, logger
from models import UserBalance, UserProfile

# Path curl absolut — jangan bergantung pada PATH proses. systemd service
# men-set Environment=PATH=.../venv/bin (tanpa /usr/bin), sehingga "curl" polos
# tidak ketemu → semua panggilan Stockity gagal. Resolusi tahan-banting:
CURL_BIN = shutil.which("curl") or next(
    (p for p in ("/usr/bin/curl", "/bin/curl", "/usr/local/bin/curl") if os.path.exists(p)),
    "curl",
)


class StockityAPIError(Exception):
    """Exception khusus untuk error Stockity API."""
    pass


class StockityAPI:
    """Client untuk API Stockity.id"""

    BASE_URL: str = STOCKITY_API_URL.rstrip("/")

    @staticmethod
    def _build_headers(
        auth_token: str,
        device_id: str,
        timezone: str = DEFAULT_TIMEZONE,
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build headers sama seperti backend NestJS."""
        headers = {
            "device-id": device_id,
            "device-type": "web",
            "user-timezone": timezone,
            "authorization-token": auth_token,
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://stockity.id",
            "Referer": "https://stockity.id/",
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    async def _curl_get(
        url: str, headers: Dict[str, str], timeout: int = 15
    ) -> Dict[str, Any]:
        """HTTP GET menggunakan curl binary (bypass Cloudflare)."""
        header_args = []
        for k, v in headers.items():
            header_args.extend(["-H", f"{k}: {v}"])

        cmd = [
            CURL_BIN, "-s", "-X", "GET", url,
            "--compressed",           # auto-decompress gzip/br dari server
            *header_args,
            "-H", "Content-Type: application/json",
            "--max-time", str(timeout),
            "-w", "\n__HTTP_STATUS__%{http_code}",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 5)
            stdout_str = stdout.decode("utf-8", errors="replace")

            parts = stdout_str.split("\n__HTTP_STATUS__")
            status_code = int(parts[1].strip() if len(parts) > 1 else "0")
            raw_body = parts[0].strip()

            if not raw_body or status_code == 0:
                raise StockityAPIError("Request timeout atau tidak ada response")

            if status_code >= 400:
                raise StockityAPIError(f"HTTP {status_code}: {raw_body[:300]}")

            try:
                parsed = json.loads(raw_body)
            except json.JSONDecodeError:
                raise StockityAPIError(f"Response bukan JSON (HTTP {status_code}): {raw_body[:300]}")

            return {"status": status_code, "data": parsed}

        except asyncio.TimeoutError:
            raise StockityAPIError("Request timeout")
        except FileNotFoundError:
            raise StockityAPIError("curl binary tidak ditemukan. Install curl: sudo apt install curl")
        except Exception as e:
            raise StockityAPIError(f"Request error: {str(e)}")

    @classmethod
    async def get_balance(
        cls, auth_token: str, device_id: str, timezone: str = DEFAULT_TIMEZONE
    ) -> UserBalance:
        """
        Ambil balance user dari Stockity API.
        Mirrors: ProfileService.getBalance()
        Endpoint: GET /bank/v1/read
        """
        url = f"{cls.BASE_URL}/bank/v1/read?locale=id"
        headers = cls._build_headers(auth_token, device_id, timezone, {
            "Cache-Control": "no-cache",
        })

        try:
            resp = await cls._curl_get(url, headers, timeout=10)
            api_data = resp["data"]

            # Extract data array
            data_list: List[Dict] = []
            if isinstance(api_data, dict):
                data_list = api_data.get("data", []) or []
            elif isinstance(api_data, list):
                data_list = api_data

            # Cari real dan demo account
            real = None
            demo = None
            for d in data_list:
                if isinstance(d, dict):
                    if d.get("account_type") == "real":
                        real = d
                    elif d.get("account_type") == "demo":
                        demo = d

            # Detect currency
            detected_currency = (
                real.get("currency") if real else None
            ) or (
                demo.get("currency") if demo else None
            ) or "IDR"

            # API mengembalikan nilai dalam satuan sen/poin terkecil, dibagi 100
            # Contoh: 20000000 → Rp 200.000 (bukan Rp 20.000.000)
            real_balance = float(real.get("balance", 0)) / 100 if real else 0
            demo_balance = float(demo.get("balance", 0)) / 100 if demo else 0

            return UserBalance(
                real_balance=real_balance,
                demo_balance=demo_balance,
                currency=detected_currency,
            )

        except StockityAPIError:
            raise
        except Exception as e:
            logger.error(f"get_balance error: {e}")
            raise StockityAPIError(f"Gagal mengambil balance: {str(e)}")

    @classmethod
    async def get_profile(
        cls, auth_token: str, device_id: str, timezone: str = DEFAULT_TIMEZONE
    ) -> UserProfile:
        """
        Ambil profile user dari Stockity API.
        Mirrors: ProfileService.getProfile()
        Menggunakan platform/private/v2/profile (lebih lengkap).
        """
        url = f"{cls.BASE_URL}/platform/private/v2/profile?locale=id"
        headers = cls._build_headers(auth_token, device_id, timezone)

        try:
            resp = await cls._curl_get(url, headers, timeout=10)
            api_data = resp["data"]

            # Navigate response structure
            profile_data = None
            if isinstance(api_data, dict):
                profile_data = api_data.get("data") or api_data
            else:
                profile_data = api_data

            if not profile_data or not isinstance(profile_data, dict):
                raise StockityAPIError("Data profile kosong")

            return UserProfile(
                id=profile_data.get("id", 0),
                email=profile_data.get("email", ""),
                first_name=profile_data.get("first_name", ""),
                last_name=profile_data.get("last_name", ""),
                username=profile_data.get("username"),
                nickname=profile_data.get("nickname"),
                phone=profile_data.get("phone"),
                gender=profile_data.get("gender"),
                country=profile_data.get("country"),
                birthday=profile_data.get("birthday"),
                registered_at=profile_data.get("registered_at") or profile_data.get("created_at"),
                avatar=profile_data.get("avatar"),
                currency=profile_data.get("currency", "IDR"),
                email_verified=profile_data.get("email_verified", False),
                phone_verified=profile_data.get("phone_verified", False),
                personal_data_locked=profile_data.get("personal_data_locked", False),
                docs_verified=profile_data.get("docs_verified", False),
            )

        except StockityAPIError:
            # Fallback ke passport/v1/user_profile
            try:
                return await cls._get_profile_v1(auth_token, device_id, timezone)
            except Exception:
                raise
        except Exception as e:
            logger.error(f"get_profile error: {e}")
            raise StockityAPIError(f"Gagal mengambil profile: {str(e)}")

    @classmethod
    async def _get_profile_v1(
        cls, auth_token: str, device_id: str, timezone: str = DEFAULT_TIMEZONE
    ) -> UserProfile:
        """Fallback: ambil profile dari endpoint v1."""
        url = f"{cls.BASE_URL}/passport/v1/user_profile?locale=id"
        headers = cls._build_headers(auth_token, device_id, timezone)

        resp = await cls._curl_get(url, headers, timeout=10)
        api_data = resp["data"]

        profile_data = None
        if isinstance(api_data, dict):
            profile_data = api_data.get("data") or api_data
        else:
            profile_data = api_data

        if not profile_data or not isinstance(profile_data, dict):
            raise StockityAPIError("Data profile v1 kosong")

        return UserProfile(
            id=profile_data.get("id", 0),
            email=profile_data.get("email", ""),
            first_name=profile_data.get("first_name", ""),
            last_name=profile_data.get("last_name", ""),
            username=profile_data.get("username"),
            nickname=profile_data.get("nickname"),
            phone=profile_data.get("phone"),
            gender=profile_data.get("gender"),
            country=profile_data.get("country"),
            birthday=profile_data.get("birthday"),
            registered_at=profile_data.get("registered_at") or profile_data.get("created_at"),
            avatar=profile_data.get("avatar"),
            currency="IDR",  # v1 tidak punya field currency
        )

    @classmethod
    async def get_user_balance_by_session(
        cls, session
    ) -> UserBalance:
        """
        Convenience method: ambil balance menggunakan session object.
        Session object harus punya: stockity_token, device_id, user_timezone
        """
        return await cls.get_balance(
            auth_token=session.stockity_token,
            device_id=session.device_id,
            timezone=session.user_timezone,
        )

    @classmethod
    async def get_user_profile_by_session(
        cls, session
    ) -> UserProfile:
        """
        Convenience method: ambil profile menggunakan session object.
        """
        return await cls.get_profile(
            auth_token=session.stockity_token,
            device_id=session.device_id,
            timezone=session.user_timezone,
        )

    # Pengaman: maksimum halaman yang diambil saat menyusuri seluruh history
    # (≈ HARD_CAP * per transaksi). Mencegah loop tak berujung kalau API aneh.
    _TXN_PAGE_HARD_CAP: int = 50

    @classmethod
    async def _get_transactions(
        cls,
        auth_token: str,
        device_id: str,
        timezone: str,
        txn_type: str,
        per: int = 50,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ambil SEMUA transaksi SUKSES bertipe `txn_type` (deposit / withdraw) dari
        Stockity API, menelusuri seluruh halaman.

        PENTING: TIDAK memakai filter `repeatable=true`. Dari HAR, parameter itu
        hanya dipakai widget "ulangi deposit" dan HANYA mengembalikan deposit yang
        bisa diulang → banyak transaksi biasa/lama TIDAK tertangkap. Itulah
        penyebab history (per-user maupun log gabungan) tidak lengkap.

        Endpoint penuh (sama dgn halaman riwayat di web):
            GET /platform/private/transactions?type=<t>&status=success&page=N&per=M
        Response: { success, data: { items: [...], count } }. `count` = jumlah
        item DI HALAMAN INI (bukan grand total), jadi paginasi berhenti saat
        sebuah halaman mengembalikan item < per (halaman terakhir) / kosong.

        Tiap item: transaction_id, amount(÷100, di-abs karena withdraw negatif),
        currency_iso, created_at(Unix detik), processed_at, handler_name, type,
        status.

        max_pages=None → telusuri SEMUA halaman (agar total benar-benar lengkap).
        max_pages=1    → cukup halaman pertama/terbaru (untuk loop deteksi
                         realtime — transaksi baru selalu muncul di paling atas).
        """
        result: List[Dict[str, Any]] = []
        seen_ids: set = set()
        page = 1

        while True:
            url = (
                f"{cls.BASE_URL}/platform/private/transactions"
                f"?type={txn_type}&status=success&per={per}&page={page}&locale=id"
            )
            headers = cls._build_headers(auth_token, device_id, timezone)

            try:
                resp = await cls._curl_get(url, headers, timeout=15)
            except StockityAPIError:
                if page == 1:
                    raise           # halaman pertama gagal → laporkan error
                break               # halaman lanjutan gagal → pakai yg sudah ada
            except Exception as e:
                if page == 1:
                    logger.error(f"_get_transactions({txn_type}) error: {e}")
                    raise StockityAPIError(f"Gagal mengambil {txn_type} transactions: {str(e)}")
                break

            api_data = resp["data"]

            # Navigasi structure: { success, data: { items: [...], count } }
            items: List[Dict] = []
            if isinstance(api_data, dict):
                inner = api_data.get("data", {})
                if isinstance(inner, dict):
                    items = inner.get("items", []) or []
                elif isinstance(inner, list):
                    items = inner
            elif isinstance(api_data, list):
                items = api_data

            if not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue
                # Pengaman ganda (server sudah filter type & status=success, tapi
                # tetap tolak tipe lain / non-sukses / amount 0 spt biaya sistem):
                itype = item.get("type")
                if itype is not None and itype != txn_type:
                    continue
                istatus = item.get("status")
                if istatus is not None and istatus != "success":
                    continue
                raw_amount = float(item.get("amount", 0) or 0)
                if raw_amount == 0:
                    continue

                txn_id = item.get("transaction_id", "")
                if txn_id and txn_id in seen_ids:
                    continue
                if txn_id:
                    seen_ids.add(txn_id)

                result.append({
                    "transaction_id": txn_id,
                    # amount dlm satuan sen/poin terkecil → ÷100; abs() krn
                    # withdraw bernilai negatif di API.
                    "amount":         abs(raw_amount) / 100,
                    "currency":       item.get("currency_iso", "IDR"),
                    "created_at":     item.get("created_at", 0),    # Unix timestamp
                    "processed_at":   item.get("processed_at", 0),
                    "handler":        item.get("handler", ""),
                    "handler_name":   item.get("handler_name", ""),
                    "status":         item.get("status", ""),
                    "type":           txn_type,
                })

            # Halaman terakhir (item < per) → selesai
            if len(items) < per:
                break
            if max_pages is not None and page >= max_pages:
                break
            if page >= cls._TXN_PAGE_HARD_CAP:
                logger.warning(
                    "_get_transactions(%s): mencapai batas %d halaman, berhenti",
                    txn_type, cls._TXN_PAGE_HARD_CAP,
                )
                break
            page += 1

        return result

    @classmethod
    async def get_deposit_transactions(
        cls,
        auth_token: str,
        device_id: str,
        timezone: str = DEFAULT_TIMEZONE,
        per: int = 50,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Ambil semua transaksi DEPOSIT sukses (lihat _get_transactions)."""
        return await cls._get_transactions(
            auth_token, device_id, timezone, "deposit", per=per, max_pages=max_pages
        )

    @classmethod
    async def get_withdraw_transactions(
        cls,
        auth_token: str,
        device_id: str,
        timezone: str = DEFAULT_TIMEZONE,
        per: int = 50,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Ambil semua transaksi PENARIKAN (withdraw) sukses (lihat _get_transactions)."""
        return await cls._get_transactions(
            auth_token, device_id, timezone, "withdraw", per=per, max_pages=max_pages
        )

    @classmethod
    async def get_deposit_transactions_by_session(
        cls, session, max_pages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Convenience: ambil deposit transactions dari session object.

        max_pages=None → seluruh history (commands tampilan).
        max_pages=1    → hanya yang terbaru (loop deteksi realtime).
        """
        return await cls.get_deposit_transactions(
            auth_token=session.stockity_token,
            device_id=session.device_id,
            timezone=session.user_timezone,
            max_pages=max_pages,
        )

    @classmethod
    async def get_withdraw_transactions_by_session(
        cls, session, max_pages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Convenience: ambil withdraw transactions dari session object."""
        return await cls.get_withdraw_transactions(
            auth_token=session.stockity_token,
            device_id=session.device_id,
            timezone=session.user_timezone,
            max_pages=max_pages,
        )


# Singleton instance
stockity_api = StockityAPI()