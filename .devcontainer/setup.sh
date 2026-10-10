#!/usr/bin/env bash
# postCreateCommand — HARUS SELALU exit 0.
# Kalau skrip ini gagal/hang (jaringan, DNS, rate-limit), codespace baru bisa
# masuk error state / recovery mode. Maka: semua bagian opsional dibungkus
# fail-safe, dan hanya bagian yang benar-benar wajib (chmod addons) yang dijalankan.
set -u

# Folder repo diturunkan dari lokasi skrip ini, BUKAN hardcode "/workspaces/Odoo-mv":
# repo ini bisa dibuka di codespace mana pun dengan nama folder apa pun
# (Odoo-mv, odoo-test, <repo>), dan folder yang salah membuat chmod di bawah
# diam-diam tidak berpengaruh.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- git aman dipakai siapa pun (root/ubuntu/codespace) ----------------------
# Tanpa ini git gagal: "detected dubious ownership in repository" — mengganggu
# agen AI dan skrip yang menjalankan git status/log.
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true
git config --global --add safe.directory "$(pwd)"     2>/dev/null || true
git config --global --add safe.directory '*'          2>/dev/null || true

# --- .env: docker compose membacanya; buat dari contoh bila belum ada --------
if [ ! -f "$REPO_DIR/.env" ] && [ -f "$REPO_DIR/.env.example" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env" 2>/dev/null || true
    echo "== .env dibuat dari .env.example (ganti password sebelum deploy) =="
fi

# --- chmod: addons wajib terbaca user `odoo` --------------------------------
# Odoo runs as user `odoo`, but files copied into the workspace may arrive
# root-owned with no read/execute bit for others (rw-r--rw- / rwxr-xrw-).
# That makes every custom addon silently unloadable by the Odoo process
# (Python import fails -> fields/views from those modules "do not exist").
for d in "$REPO_DIR/addons" "$REPO_DIR/import_data"; do
    if [ -d "$d" ]; then
        chmod -R a+rX "$d" 2>/dev/null || true
    fi
done

# --- OpenCode CLI (opsional — kegagalannya TIDAK boleh menggagalkan codespace)
if command -v opencode >/dev/null 2>&1; then
    echo "== OpenCode CLI sudah terpasang: $(command -v opencode) =="
else
    echo "== Installing OpenCode CLI (opsional, maks 120 detik) =="
    if timeout 120 curl -fsSL --retry 2 --connect-timeout 10 https://opencode.ai/install | bash; then
        echo "== OpenCode terpasang =="
    else
        echo "!! Instalasi OpenCode gagal/timeout — TIDAK fatal. Jalankan manual nanti:" >&2
        echo "!!   curl -fsSL https://opencode.ai/install | bash" >&2
    fi
fi

echo "== Done. Odoo will be reachable on port 8069 once containers finish starting. =="
echo "== Run 'opencode' in this folder, then /connect to choose a provider =="
echo "== (select Ox Alpha via /models once connected). =="

# Selalu sukses — jangan pernah biarkan postCreateCommand menggagalkan codespace.
exit 0
