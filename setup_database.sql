-- ============================================================
-- SETUP DATABASE UNTUK TELEGRAM ADMIN BOT
-- Jalankan di SQL Editor Supabase
-- ============================================================

-- 1. Tabel admin bot Telegram
-- ============================================================
CREATE TABLE IF NOT EXISTS bot_admins (
    chat_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT DEFAULT 'admin' CHECK (role IN ('admin', 'super_admin')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by BIGINT
);

-- Comment untuk dokumentasi
COMMENT ON TABLE bot_admins IS 'Admin yang bisa mengakses bot Telegram';
COMMENT ON COLUMN bot_admins.chat_id IS 'Telegram chat ID dari admin';
COMMENT ON COLUMN bot_admins.role IS 'admin atau super_admin';

-- 2. Tabel balance history untuk tracking deposit
-- ============================================================
CREATE TABLE IF NOT EXISTS balance_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    email TEXT,
    real_balance NUMERIC DEFAULT 0,
    demo_balance NUMERIC DEFAULT 0,
    currency TEXT DEFAULT 'IDR',
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_balance_history_user_id 
    ON balance_history(user_id);
CREATE INDEX IF NOT EXISTS idx_balance_history_checked_at 
    ON balance_history(checked_at DESC);

COMMENT ON TABLE balance_history IS 'Snapshot balance untuk deteksi perubahan/deposit';

-- 3. Tabel deposit events
-- ============================================================
CREATE TABLE IF NOT EXISTS deposit_events (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    email TEXT,
    amount NUMERIC NOT NULL,
    currency TEXT DEFAULT 'IDR',
    previous_balance NUMERIC DEFAULT 0,
    new_balance NUMERIC DEFAULT 0,
    -- transaction_id: ID unik transaksi Stockity. WAJIB ada — bot meng-upsert
    -- on_conflict=transaction_id. Tanpa kolom ini semua penyimpanan deposit gagal.
    transaction_id TEXT,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deposit_events_user_id
    ON deposit_events(user_id);
CREATE INDEX IF NOT EXISTS idx_deposit_events_detected_at
    ON deposit_events(detected_at DESC);
-- Unique agar upsert(on_conflict="transaction_id") bekerja & anti-duplikat.
CREATE UNIQUE INDEX IF NOT EXISTS idx_deposit_events_txn_id
    ON deposit_events(transaction_id);

COMMENT ON TABLE deposit_events IS 'Event deposit yang terdeteksi oleh bot';

-- 4. Enable Realtime untuk tabel yang perlu di-listen
-- ============================================================
-- Pastikan tabel whitelist_users sudah ada realtime
-- (biasanya sudah di-setup di backend NestJS)

-- Tambahkan tabel ke supabase realtime publication jika belum
DO $$
BEGIN
    -- Cek apakah publication ada
    IF EXISTS (
        SELECT 1 FROM pg_publication 
        WHERE pubname = 'supabase_realtime'
    ) THEN
        -- Cek apakah tabel sudah ditambahkan
        IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
            WHERE pubname = 'supabase_realtime'
            AND tablename = 'whitelist_users'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE whitelist_users;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
            WHERE pubname = 'supabase_realtime'
            AND tablename = 'bot_admins'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE bot_admins;
        END IF;
    END IF;
END $$;

-- 5. Row Level Security (RLS) - WAJIB: kunci ke service_role saja
-- ============================================================
-- Bot memakai Service Role Key yang BYPASS RLS → bot tetap berjalan normal.
-- RLS ON + 0 policy = role `anon` & `authenticated` DITOLAK total.
--
-- ⚠️ JANGAN buat policy "USING (true)" di tabel ini. Anon key publik ter-embed
-- di bundle frontend; policy permisif akan membuat siapa pun bisa:
--   - INSERT dirinya ke bot_admins sebagai super_admin → ambil alih bot Telegram,
--   - membaca deposit_events (email + nominal deposit) & chat_id admin.
-- Pola ini selaras dengan stcvps/src/supabase/lockdown-backend-tables.sql.

ALTER TABLE bot_admins      ENABLE ROW LEVEL SECURITY;
ALTER TABLE balance_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE deposit_events  ENABLE ROW LEVEL SECURITY;

-- Cabut policy permisif lama jika pernah dibuat (idempoten, aman dijalankan ulang).
DROP POLICY IF EXISTS "Allow all" ON bot_admins;
DROP POLICY IF EXISTS "Allow all" ON balance_history;
DROP POLICY IF EXISTS "Allow all" ON deposit_events;

-- ============================================================
-- SEED DATA (Opsional)
-- ============================================================

-- Jika Anda sudah tahu chat ID super admin, bisa insert manual:
-- INSERT INTO bot_admins (chat_id, username, first_name, role, is_active, created_at)
-- VALUES (123456789, 'your_username', 'Your Name', 'super_admin', true, NOW());

-- Atau biarkan auto-register saat pertama kali /start di bot
