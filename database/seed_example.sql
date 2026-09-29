-- ============================================================
-- HELPER: Generate API key untuk server baru
-- Jalankan: mysql -u root -p < generate_api_keys.sql
-- Output akan menunjukkan contoh INSERT statement
-- ============================================================

-- Contoh API Key untuk testing (dibuat dengan hex random 64 char)
-- Ganti dengan key yang di-generate secara runtime di Python

-- Contoh generate via SQL:
SELECT HEX(RANDOM_BYTES(32)) AS api_key_example;

-- Contoh seed data (ganti api_key dengan hasil generate di atas):
-- INSERT INTO servers (hostname, ip_address, api_key) VALUES
-- ('web-prod-01', '192.168.1.10', '<paste_api_key_disini>'),
-- ('db-prod-01',  '192.168.1.20', '<paste_api_key_disini>');
