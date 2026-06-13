# 🤖 Telegram Admin Bot

Bot Telegram berbasis Python untuk monitoring dan manajemen sistem trading. Berjalan di VPS Ubuntu dengan integrasi ke Supabase dan Stockity API.

## ✨ Fitur

### 📢 Notifikasi Real-time
- **User Baru** - Notifikasi saat user baru mendaftar atau ditambahkan admin
- **Deposit** - Deteksi dan notifikasi deposit akun real secara otomatis
- **Broadcast** - Kirim pesan ke semua admin bot

### 💰 Manajemen Saldo
- Cek saldo akun real by user ID
- Cek saldo by email
- Filter dan pencarian user
- History deposit 24 jam / 7 hari

### 👥 Manajemen User
- Daftar semua user whitelist
- Detail user lengkap (profile + saldo + status)
- Cari user by keyword
- Aktifkan/nonaktifkan user

### 👑 Manajemen Admin
- Multi-level admin (admin & super_admin)
- Tambah/hapus admin bot
- Aktifkan/nonaktifkan admin
- Auto-register super admin pertama

### 📊 Statistik
- Total user, user aktif/nonaktif
- User yang login dalam 24 jam terakhir
- User baru dalam 24 jam terakhir
- Statistik session

## 🚀 Instalasi Cepat

### Prerequisites
- VPS Ubuntu 20.04/22.04/24.04
- Python 3.10+
- curl (untuk bypass Cloudflare)
- Token Bot Telegram (dari [@BotFather](https://t.me/BotFather))

### Otomatis (Recommended)

```bash
# 1. Clone/copy project ke VPS
cd /opt
git clone <repo-url> telegram-admin-bot
cd telegram-admin-bot

# 2. Jalankan installer
sudo bash install.sh

# 3. Ikuti prompt konfigurasi

# 4. Start bot
sudo systemctl start telegram-admin-bot
```

### Manual

```bash
# 1. Install dependencies
sudo apt update
sudo apt install python3 python3-venv python3-pip curl -y

# 2. Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python packages
pip install -r requirements.txt

# 4. Konfigurasi .env
cp .env.example .env
nano .env  # Edit konfigurasi

# 5. Jalankan bot
python src/main.py
```

## ⚙️ Konfigurasi (.env)

| Variable | Wajib | Default | Deskripsi |
|----------|-------|---------|-----------|
| `TELEGRAM_BOT_TOKEN` | ✅ | - | Token dari @BotFather |
| `SUPABASE_URL` | ✅ | - | URL Supabase project |
| `SUPABASE_SERVICE_KEY` | ✅ | - | Service Role Key |
| `STOCKITY_API_URL` | ❌ | `https://api.stockity.id` | Base URL API Stockity |
| `SUPER_ADMIN_CHAT_IDS` | ❌ | - | Chat ID super admin (pisah koma) |
| `NOTIFICATION_CHANNEL_ID` | ❌ | - | Channel/group untuk broadcast |
| `BOT_MODE` | ❌ | `polling` | `polling` atau `webhook` |
| `DEPOSIT_CHECK_INTERVAL` | ❌ | `300` | Interval cek deposit (detik) |
| `MIN_DEPOSIT_AMOUNT` | ❌ | `1` | Minimum deposit terdeteksi |

## 📋 Daftar Perintah

### Manajemen Admin
| Perintah | Akses | Deskripsi |
|----------|-------|-----------|
| `/admins` | Admin | Daftar admin bot |
| `/addadmin [chat_id]` | Super Admin | Tambah admin baru |
| `/removeadmin [chat_id]` | Super Admin | Hapus admin |
| `/toggleadmin [chat_id]` | Super Admin | Aktifkan/nonaktifkan admin |

### Manajemen User
| Perintah | Akses | Deskripsi |
|----------|-------|-----------|
| `/users [limit] [offset]` | Admin | Daftar user whitelist |
| `/user [id/email]` | Admin | Detail user lengkap |
| `/search [keyword]` | Admin | Cari user |
| `/aktifkan [email]` | Admin | Aktifkan user |
| `/nonaktifkan [email]` | Admin | Nonaktifkan user |

### Saldo & Deposit
| Perintah | Akses | Deskripsi |
|----------|-------|-----------|
| `/saldo [user_id]` | Admin | Cek saldo by ID |
| `/saldobyemail [email]` | Admin | Cek saldo by email |
| `/depositlog` | Admin | Log deposit 24 jam |
| `/depositlog7` | Admin | Log deposit 7 hari |

### Statistik
| Perintah | Akses | Deskripsi |
|----------|-------|-----------|
| `/stats` | Admin | Statistik sistem |
| `/cekstatus [user_id]` | Admin | Status lengkap user |

### Komunikasi
| Perintah | Akses | Deskripsi |
|----------|-------|-----------|
| `/broadcast [pesan]` | Admin | Kirim ke semua admin |

### Utilitas
| Perintah | Akses | Deskripsi |
|----------|-------|-----------|
| `/start` | Siapa saja | Mulai bot / register |
| `/help` | Admin | Daftar perintah |
| `/ping` | Admin | Cek status |
| `/myid` | Siapa saja | Lihat chat ID |

## 🛠️ Manajemen Service

```bash
# Status bot
sudo systemctl status telegram-admin-bot

# Start bot
sudo systemctl start telegram-admin-bot

# Stop bot
sudo systemctl stop telegram-admin-bot

# Restart bot
sudo systemctl restart telegram-admin-bot

# Auto-start saat boot
sudo systemctl enable telegram-admin-bot

# Lihat log real-time
sudo journalctl -u telegram-admin-bot -f

# Lihat log terakhir 100 baris
sudo journalctl -u telegram-admin-bot -n 100
```

## 🗄️ Struktur Database (Supabase)

Bot menggunakan tabel yang sudah ada di Supabase + beberapa tabel tambahan:

### Tabel Existing (dari sistem)
- `sessions` - Data user login
- `whitelist_users` - User whitelist
- `admin_users` - Admin sistem
- `super_admins` - Super admin

### Tabel Baru (otomatis dibuat)

```sql
-- Admin bot Telegram
CREATE TABLE bot_admins (
    chat_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT DEFAULT 'admin' CHECK (role IN ('admin', 'super_admin')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by BIGINT
);

-- History balance untuk deteksi deposit
CREATE TABLE balance_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    email TEXT,
    real_balance NUMERIC DEFAULT 0,
    demo_balance NUMERIC DEFAULT 0,
    currency TEXT DEFAULT 'IDR',
    checked_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_balance_history_user_id ON balance_history(user_id);
CREATE INDEX idx_balance_history_checked_at ON balance_history(checked_at DESC);

-- Deposit events
CREATE TABLE deposit_events (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    email TEXT,
    amount NUMERIC NOT NULL,
    currency TEXT DEFAULT 'IDR',
    previous_balance NUMERIC DEFAULT 0,
    new_balance NUMERIC DEFAULT 0,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_deposit_events_user_id ON deposit_events(user_id);
CREATE INDEX idx_deposit_events_detected_at ON deposit_events(detected_at DESC);
```

## 🔒 Keamanan

- Hanya admin yang terdaftar yang bisa akses bot
- Super admin punya akses penuh
- Admin biasa tidak bisa mengelola admin lain
- Semua command dilog
- `.env` file harus chmod 600

## 🔧 Troubleshooting

### Bot tidak bisa start
```bash
# Cek konfigurasi
sudo journalctl -u telegram-admin-bot -n 50

# Cek .env
sudo cat /opt/telegram-admin-bot/.env | grep -v KEY | grep -v TOKEN

# Cek Python
sudo /opt/telegram-admin-bot/venv/bin/python --version
```

### Tidak bisa ambil saldo user
- Pastikan session user masih aktif (belum logout)
- Cek curl terinstall: `which curl`
- Cek koneksi ke Stockity API

### Notifikasi tidak muncul
- Cek bot_admins tabel
- Cek log: `sudo journalctl -u telegram-admin-bot -f`
- Pastikan deposit check interval tidak terlalu lama

## 📁 Struktur Project

```
telegram-admin-bot/
├── src/
│   ├── main.py           # Entry point
│   ├── config.py         # Konfigurasi & logging
│   ├── models.py         # Data models
│   ├── database.py       # Supabase client
│   ├── stockity_api.py   # Stockity API wrapper
│   ├── notifications.py  # Notifikasi service
│   └── handlers.py       # Command handlers
├── logs/                 # Log files
├── .env                  # Environment variables
├── .env.example          # Contoh konfigurasi
├── requirements.txt      # Python dependencies
├── install.sh            # Script instalasi
├── telegram-admin-bot.service  # Systemd service
└── README.md             # Dokumentasi
```

## 📝 Changelog

### v1.0.0
- ✨ Rilis awal
- 📢 Notifikasi user baru & deposit
- 💰 Cek saldo by ID/email
- 👥 Manajemen user & admin
- 📊 Statistik sistem

## 📄 Lisensi

Proprietary - Internal Use Only
