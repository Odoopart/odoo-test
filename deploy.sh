#!/usr/bin/env bash
# =============================================================================
# deploy.sh - pembantu deploy stack Odoo 19 (Docker) untuk proyek Geprekyukss.
#
# Pemakaian:
#   ./deploy.sh up            # build + jalankan semua service (background)
#   ./deploy.sh down          # hentikan & hapus container (data tetap aman)
#   ./deploy.sh restart       # restart Odoo
#   ./deploy.sh logs          # ikuti log Odoo
#   ./deploy.sh ps            # status container
#   ./deploy.sh init          # buat DB + install modul custom (sekali saja)
#   ./deploy.sh update        # upgrade modul custom setelah ubah kode Python/XML
#   ./deploy.sh shell         # masuk Odoo shell
#   ./deploy.sh backup        # dump DB + filestore ke folder backups/
#   ./deploy.sh restore DIR   # pulihkan dari folder hasil backup
#
# File .env otomatis dibuat dari .env.example pada perintah pertama.
# =============================================================================
set -euo pipefail

COMPOSE="docker compose"
DB_NAME="geprekyukss"
DB_USER="odoo"

need_env() {
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "!! .env dibuat dari .env.example."
        echo "!! Edit dulu: nano .env  (ganti POSTGRES_PASSWORD & ODOO_ADMIN_PASSWD), lalu ulangi perintah."
        exit 1
    fi
    # Muat variabel dari .env untuk keperluan script (compose membacanya sendiri).
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
    DB_NAME="${ODOO_DB_NAME:-geprekyukss}"
    DB_USER="${POSTGRES_USER:-odoo}"
}

usage() {
    grep -E '^#   ' "$0" | sed 's/^#   //'
}

CMD="${1:-help}"
case "$CMD" in
    up)
        need_env
        $COMPOSE up -d --build
        echo "Odoo siap di http://localhost:${ODOO_PORT:-8069}"
        echo "Jika DB belum ada, jalankan: ./deploy.sh init"
        ;;
    down)
        $COMPOSE down
        ;;
    restart)
        $COMPOSE restart odoo
        ;;
    logs)
        $COMPOSE logs -f --tail=100 odoo
        ;;
    ps)
        $COMPOSE ps
        ;;
    build)
        $COMPOSE build
        ;;
    init)
        need_env
        echo "==> Membuat database '$DB_NAME' + install modul custom (tanpa data demo)..."
        $COMPOSE up -d db
        $COMPOSE run --rm odoo odoo -d "$DB_NAME" \
            -i geprekyukss_dashboard,geprekyukss_home \
            --without-demo=all --stop-after-init
        $COMPOSE up -d odoo
        echo "==> Selesai. Buka http://localhost:${ODOO_PORT:-8069}"
        ;;
    update)
        need_env
        echo "==> Upgrade modul custom pada database '$DB_NAME'..."
        $COMPOSE run --rm odoo odoo -d "$DB_NAME" \
            -u geprekyukss_dashboard,geprekyukss_pos,geprekyukss_home --stop-after-init
        $COMPOSE restart odoo
        ;;
    shell)
        need_env
        $COMPOSE exec odoo odoo shell -d "$DB_NAME"
        ;;
    backup)
        need_env
        $COMPOSE up -d
        TS="$(date +%Y%m%d_%H%M%S)"
        OUT="backups/${DB_NAME}_${TS}"
        mkdir -p "$OUT"
        echo "==> Dump database -> $OUT/dump.pgc"
        $COMPOSE exec -T db pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$OUT/dump.pgc"
        echo "==> Arsip filestore -> $OUT/filestore.tar.gz"
        $COMPOSE exec -T odoo tar czf - -C /var/lib/odoo "filestore/${DB_NAME}" \
            > "$OUT/filestore.tar.gz" 2>/dev/null || echo "    (filestore kosong/dilewati)"
        echo "==> Backup selesai: $OUT"
        ;;
    restore)
        need_env
        SRC="${2:-}"
        if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
            echo "Pakai: ./deploy.sh restore backups/<folder>"
            exit 1
        fi
        [ -f "$SRC/dump.pgc" ] || { echo "ERROR: $SRC/dump.pgc tidak ditemukan"; exit 1; }
        echo "==> Menghapus & membuat ulang database '$DB_NAME' (DESTRUKTIF)..."
        $COMPOSE stop odoo 2>/dev/null || true
        $COMPOSE up -d db
        $COMPOSE exec -T db psql -U "$DB_USER" -d postgres -c \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}';"
        $COMPOSE exec -T db psql -U "$DB_USER" -d postgres -c \
            "DROP DATABASE IF EXISTS \"${DB_NAME}\";"
        $COMPOSE exec -T db psql -U "$DB_USER" -d postgres -c \
            "CREATE DATABASE \"${DB_NAME}\" OWNER ${DB_USER} TEMPLATE template0 ENCODING UTF8;"
        echo "==> Restore dump..."
        $COMPOSE exec -T db pg_restore -U "$DB_USER" --no-owner --role="$DB_USER" \
            --exit-on-error --dbname="$DB_NAME" < "$SRC/dump.pgc"
        if [ -f "$SRC/filestore.tar.gz" ]; then
            echo "==> Restore filestore..."
            $COMPOSE exec -T odoo tar xzf - -C /var/lib/odoo < "$SRC/filestore.tar.gz"
        fi
        $COMPOSE up -d odoo
        echo "==> Restore selesai."
        ;;
    help|*)
        usage
        ;;
esac
