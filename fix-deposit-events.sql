-- ============================================================
-- FIX: tabel deposit_events kurang kolom `transaction_id`
-- ============================================================
-- Bot menulis `transaction_id` + upsert on_conflict=transaction_id ke
-- deposit_events (lihat database.py save_deposit_event). Karena kolomnya
-- TIDAK ADA, setiap penyimpanan deposit GAGAL diam-diam → /depositlog &
-- /depositlog7 selalu kosong. Inilah sebab "gagal dapat info deposit terakhir".
--
-- Jalankan SEKALI di Supabase SQL Editor, lalu restart bot.
-- ============================================================

ALTER TABLE deposit_events ADD COLUMN IF NOT EXISTS transaction_id TEXT;

-- Unique index WAJIB agar upsert(on_conflict="transaction_id") bekerja
-- sekaligus mencegah duplikat saat bot restart. NULL diperbolehkan ganda
-- (baris lama tanpa transaction_id tidak terganggu).
CREATE UNIQUE INDEX IF NOT EXISTS idx_deposit_events_txn_id
    ON deposit_events (transaction_id);

-- Verifikasi:
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'deposit_events' AND column_name = 'transaction_id';
