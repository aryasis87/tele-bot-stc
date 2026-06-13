#!/bin/bash
# ============================================================
# INSTALL SCRIPT - Telegram Admin Bot
# Untuk VPS Ubuntu 20.04/22.04/24.04
# ============================================================

set -e

# Warna
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="telegram-admin-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="$BOT_DIR/venv"

echo -e "${BLUE}"
echo "============================================================"
echo "  INSTALASI TELEGRAM ADMIN BOT"
echo "============================================================"
echo -e "${NC}"

# --- Check root ---
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Harus dijalankan sebagai root (gunakan sudo)${NC}"
    exit 1
fi

# --- Check OS ---
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    echo -e "${YELLOW}⚠️ Script ini dioptimalkan untuk Ubuntu${NC}"
    read -p "Lanjutkan? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${BLUE}📁 Direktori bot: $BOT_DIR${NC}"

# ============================================================
# STEP 1: Install system dependencies
# ============================================================
echo -e "\n${BLUE}[1/7] Menginstall dependencies sistem...${NC}"
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    curl \
    git \
    systemd \
    > /dev/null 2>&1
echo -e "${GREEN}✅ Dependencies sistem terinstall${NC}"

# ============================================================
# STEP 2: Create virtual environment
# ============================================================
echo -e "\n${BLUE}[2/7] Membuat virtual environment...${NC}"
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚠️ Virtual environment sudah ada, melewati...${NC}"
else
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ Virtual environment dibuat${NC}"
fi

# ============================================================
# STEP 3: Install Python packages
# ============================================================
echo -e "\n${BLUE}[3/7] Menginstall Python packages...${NC}"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
echo -e "${GREEN}✅ Python packages terinstall${NC}"

# ============================================================
# STEP 4: Setup .env file
# ============================================================
echo -e "\n${BLUE}[4/7] Konfigurasi environment...${NC}"

ENV_FILE="$BOT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}⚠️ File .env sudah ada${NC}"
    read -p "Timpa konfigurasi? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}⏭️ Melewati konfigurasi .env${NC}"
        SKIP_ENV=1
    fi
fi

if [ -z "$SKIP_ENV" ]; then
    echo -e "${BLUE}📝 Silakan masukkan konfigurasi bot:${NC}\n"

    # Bot Token
    while [ -z "$BOT_TOKEN" ]; do
        read -p "Telegram Bot Token (dari @BotFather): " BOT_TOKEN
        if [ -z "$BOT_TOKEN" ]; then
            echo -e "${RED}❌ Bot token wajib diisi!${NC}"
        fi
    done

    # Supabase
    read -p "Supabase URL: " SUPABASE_URL
    read -p "Supabase Service Role Key: " SUPABASE_KEY

    # Stockity API
    read -p "Stockity API URL [https://api.stockity.id]: " STOCKITY_URL
    STOCKITY_URL=${STOCKITY_URL:-"https://api.stockity.id"}

    # Super Admin Chat IDs
    read -p "Super Admin Chat IDs (pisah koma, kosongkan untuk auto-register): " ADMIN_IDS

    # Notifikasi channel
    read -p "Notification Channel/Group ID (opsional): " CHANNEL_ID

    # Mode
    read -p "Bot Mode [polling/webhook]: " MODE
    MODE=${MODE:-"polling"}

    # Deposit check interval
    read -p "Deposit Check Interval detik [300]: " CHECK_INTERVAL
    CHECK_INTERVAL=${CHECK_INTERVAL:-"300"}

    # Write .env
    cat > "$ENV_FILE" <<EOF
# ============================================================
# CONFIGURASI BOT TELEGRAM ADMIN
# ============================================================

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN=$BOT_TOKEN

# --- Supabase ---
SUPABASE_URL=$SUPABASE_URL
SUPABASE_SERVICE_KEY=$SUPABASE_KEY

# --- API Stockity ---
STOCKITY_API_URL=$STOCKITY_URL

# --- Admin Bot Config ---
SUPER_ADMIN_CHAT_IDS=$ADMIN_IDS
NOTIFICATION_CHANNEL_ID=$CHANNEL_ID

# --- Mode Operasi ---
BOT_MODE=$MODE

# --- Deposit Detection ---
DEPOSIT_CHECK_INTERVAL=$CHECK_INTERVAL
MIN_DEPOSIT_AMOUNT=1

# --- Logging ---
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
EOF

    chmod 600 "$ENV_FILE"
    echo -e "${GREEN}✅ File .env dibuat${NC}"
fi

# ============================================================
# STEP 5: Create logs directory
# ============================================================
echo -e "\n${BLUE}[5/7] Membuat direktori logs...${NC}"
mkdir -p "$BOT_DIR/logs"
chmod 755 "$BOT_DIR/logs"
echo -e "${GREEN}✅ Direktori logs dibuat${NC}"

# ============================================================
# STEP 6: Setup systemd service
# ============================================================
echo -e "\n${BLUE}[6/7] Membuat systemd service...${NC}"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Telegram Admin Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
Environment=PATH=$VENV_DIR/bin
ExecStart=$VENV_DIR/bin/python $BOT_DIR/src/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegram-admin-bot

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo -e "${GREEN}✅ Service systemd dibuat dan di-enable${NC}"

# ============================================================
# STEP 7: Verifikasi dan instruksi
# ============================================================
echo -e "\n${BLUE}[7/7] Verifikasi instalasi...${NC}"

# Check Python version
PY_VERSION=$($VENV_DIR/bin/python --version 2>&1)
echo -e "${GREEN}✅ $PY_VERSION${NC}"

# Check curl
if command -v curl &> /dev/null; then
    CURL_VERSION=$(curl --version | head -1)
    echo -e "${GREEN}✅ $CURL_VERSION${NC}"
else
    echo -e "${RED}❌ curl tidak ditemukan!${NC}"
fi

echo -e "\n${GREEN}"
echo "============================================================"
echo "  ✅ INSTALASI SELESAI!"
echo "============================================================"
echo -e "${NC}"
echo -e "${BLUE}Perintah yang tersedia:${NC}"
echo -e "  ${YELLOW}sudo systemctl start $SERVICE_NAME${NC}  - Mulai bot"
echo -e "  ${YELLOW}sudo systemctl stop $SERVICE_NAME${NC}   - Hentikan bot"
echo -e "  ${YELLOW}sudo systemctl status $SERVICE_NAME${NC} - Status bot"
echo -e "  ${YELLOW}sudo journalctl -u $SERVICE_NAME -f${NC} - Lihat log"
echo ""
echo -e "${BLUE}File penting:${NC}"
echo -e "  📁 Bot: $BOT_DIR"
echo -e "  ⚙️  Config: $BOT_DIR/.env"
echo -e "  📝 Logs: $BOT_DIR/logs/"
echo -e "  🔧 Service: $SERVICE_FILE"
echo ""
echo -e "${GREEN}Untuk memulai bot, jalankan:${NC}"
echo -e "  ${YELLOW}sudo systemctl start $SERVICE_NAME${NC}"
echo ""
echo -e "${BLUE}Bot akan otomatis start saat boot.${NC}"
