# Geprekyukss — Odoo 19 (Docker)

Odoo 19 Community + PostgreSQL 15, semua modul custom/OCA ada di `addons/`.
Seluruh stack berjalan lewat Docker sehingga mudah dipindah ke server/VPS mana pun.

## Isi file Docker

| File | Fungsi |
|------|--------|
| `Dockerfile` | Image Odoo 19 + dependensi Python modul OCA (xlsxwriter, freezegun, dll.) |
| `docker-compose.yml` | Service `odoo` + `db`, volume permanen, healthcheck |
| `.env.example` | Template kredensial & konfigurasi (salin jadi `.env`) |
| `deploy.sh` | Perintah praktis: up / down / init / update / backup / restore |

## Cara deploy (server baru)

```bash
git clone <url-repo> && cd <folder-repo>
cp .env.example .env
nano .env                 # WAJIB ganti POSTGRES_PASSWORD & ODOO_ADMIN_PASSWD
./deploy.sh up            # build image + jalankan
./deploy.sh init          # buat database + install modul custom
```

Buka `http://IP-SERVER:8069`. Login admin pertama dibuat saat `init` (email/password
ditampilkan di log bila perlu, atau daftar lewat halaman login).

> Tanpa data demo. Database default: `geprekyukss` (ubah `ODOO_DB_NAME` di `.env`).

## Perintah harian

```bash
./deploy.sh ps          # status container
./deploy.sh logs        # lihat log Odoo (Ctrl+C untuk keluar)
./deploy.sh restart     # restart Odoo
./deploy.sh down        # hentikan (data TIDAK hilang)
./deploy.sh up          # jalankan lagi
```

## Update modul setelah ubah kode

- Ubah file **Python/XML** → wajib upgrade:
  ```bash
  ./deploy.sh update
  ```
- Ubah file **JS/SCSS/template POS** → cukup refresh browser (hard reload).

## Backup & restore

```bash
./deploy.sh backup                 # -> backups/<db>_<tanggal>/ (dump.pgc + filestore.tar.gz)
./deploy.sh restore backups/<db>_<tanggal>
```

Alternatif paling mudah: menu **Database Manager** Odoo → *Backup* (menghasilkan
satu file `.zip` yang bisa di-restore lewat UI).

## Catatan untuk produksi

- Ganti semua password default di `.env` sebelum online.
- Pakai domain + HTTPS: taruh reverse proxy (mis. Nginx/Caddy) di depan port `8069`.
- Untuk trafik banyak, set `ODOO_WORKERS` = `2 * jumlah CPU + 1` di `.env`, lalu `./deploy.sh up`.
- Batasi DB yang tampil: set `ODOO_DB_FILTER=^geprekyukss$`.
- Jangan commit `.env`, folder `backups/`, atau data database (sudah ada di `.gitignore`).

## Struktur singkat

```
addons/            # modul custom (geprekyukss_pos, geprekyukss_dashboard) + OCA
Dockerfile         # definisi image
docker-compose.yml # orkestrasi odoo + db
deploy.sh          # perintah deploy
.env               # kredensial (dibuat dari .env.example, tidak di-commit)
```
