# -*- coding: utf-8 -*-
{
    "name": "Geprekyukss - Home Menu",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "summary": "Halaman awal kustom: jam, pengumuman, dan grid aplikasi terpasang",
    "description": """
Menggantikan halaman awal Odoo (Community) dengan Home Menu kustom:
- Kartu tanggal + jam berdetak dan kolom pengumuman yang tersimpan di server.
- Grid ikon semua aplikasi yang boleh diakses user yang sedang login.
- Tampil setelah login dan saat tombol Menu di navbar diklik.
""",
    "author": "Custom - Geprekyukss",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "data/home_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "geprekyukss_home/static/src/home/**/*.js",
            "geprekyukss_home/static/src/home/**/*.xml",
            "geprekyukss_home/static/src/navbar/**/*.js",
            "geprekyukss_home/static/src/navbar/**/*.xml",
            "geprekyukss_home/static/src/scss/home_menu.scss",
        ],
    },
    "installable": True,
    "application": False,
}
