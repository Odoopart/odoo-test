# -*- coding: utf-8 -*-
{
    "name": "Geprekyukss - PBJT (Pajak Daerah F&B)",
    "version": "19.0.1.1.0",
    "category": "Accounting/Localizations",
    "summary": "PBJT Makanan & Minuman (Pajak Restoran) per outlet + laporan rekonsiliasi",
    "description": """
Modul PBJT (Pajak Barang dan Jasa Tertentu atas Makanan dan/atau Minuman)
untuk F&B multi-outlet Geprekyukss.

Dasar hukum: Perda Kota Makassar No. 1 Tahun 2024 (Pasal 60) - tarif PBJT
makanan/minuman 10%, pengecualian peredaran usaha <= Rp 5.000.000/bulan.
UU No. 1 Tahun 2022 (HKPD).

Cakupan: konfigurasi PBJT per outlet (tarif, harga termasuk/eksklusif, batas
bebas, akun utang, pajak terkait); rekonsiliasi PBJT per outlet & periode
(penjualan bruto, DPP, PBJT riil, nilai negoisasi/dibayar ke Bapenda, selisih);
penerapan otomatis pajak PBJT pada produk POS (menggantikan PPN warisan).
""",
    "author": "Custom - Geprekyukss",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/pbjt_data.xml",
        "views/pbjt_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
}
