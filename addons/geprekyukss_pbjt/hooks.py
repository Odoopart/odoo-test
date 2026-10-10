# -*- coding: utf-8 -*-
"""Post-install: siapkan konfigurasi PBJT per outlet & terapkan pajak ke POS."""
import logging

_logger = logging.getLogger(__name__)

# Tarif & kebijakan default (Perda Kota Makassar No. 1 Tahun 2024).
DEFAULT_RATE = 10.0
DEFAULT_PRICE_INCLUDE = True
DEFAULT_EXEMPT = 5000000.0


def post_init_hook(env):
    """Jalankan sekali saat modul di-install.

    1. Buat `pbjt.outlet.config` untuk setiap pos.config yang belum punya.
    2. Terapkan pajak PBJT ke semua produk POS (menggantikan PPN warisan).
    """
    Config = env["pbjt.outlet.config"]
    tax = env.ref("geprekyukss_pbjt.tax_pbjt_10", raise_if_not_found=False)
    account = env.ref("geprekyukss_pbjt.account_pbjt_payable", raise_if_not_found=False)

    configs = Config.browse()
    for pos_config in env["pos.config"].search([]):
        existing = Config.search([("pos_config_id", "=", pos_config.id)], limit=1)
        if existing:
            configs |= existing
            continue
        configs |= Config.create(
            {
                "pos_config_id": pos_config.id,
                "rate": DEFAULT_RATE,
                "price_include": DEFAULT_PRICE_INCLUDE,
                "exempt_omzet_month": DEFAULT_EXEMPT,
                "tax_id": tax.id if tax else False,
                "liability_account_id": account.id if account else False,
            }
        )
    _logger.info("PBJT: %s konfigurasi outlet dibuat/dipastikan.", len(configs))

    if tax:
        for cfg in configs:
            cfg.action_apply_tax_to_pos_products()
        _logger.info("PBJT: pajak %s diterapkan ke produk POS.", tax.name)
