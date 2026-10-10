# Image Odoo 19 + dependensi Python untuk modul OCA di folder addons/.
# Deploy: docker compose build && docker compose up -d
FROM odoo:19

USER root

# Paket ini dibutuhkan modul OCA (report_xlsx, account_asset_management,
# account_journal_general_sequence). xlrd sudah ada di image dasar.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        python3-xlsxwriter \
        python3-dateutil \
        python3-freezegun \
    ; \
    rm -rf /var/lib/apt/lists/*

USER odoo
