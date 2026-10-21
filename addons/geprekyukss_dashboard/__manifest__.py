# -*- coding: utf-8 -*-
{
    "name": "Geprekyukss - Financial Dashboard",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "summary": "Dashboard laporan keuangan live (4 tab) + report shell AFR/MIS untuk Geprekyukss",
    "description": """
Dashboard laporan keuangan live per bulan — Ringkasan Eksekutif, Detail Keuangan,
Penjualan & Channel, Aset & Operasional. Data parametrik (pilih bulan), bukan
laporan statis.
""",
    "author": "Custom - Geprekyukss",
    "license": "LGPL-3",
    "depends": [
        "geprekyukss_pos",
        "geprekyukss_pbjt",
        "stock",
        "account_asset_management",
        "mis_builder_cash_flow",
        "report_xlsx",
    ],
    "data": [
        "views/menus.xml",
        "data/mis_report_pl.xml",
        "data/mis_report_bs.xml",
        "data/mis_report_cf_labels.xml",
        "report/mgmt_multi_outlet_templates.xml",
        "data/mgmt_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            ("include", "web.chartjs_lib"),
            "geprekyukss_dashboard/static/src/app/dashboard/**/*.js",
            "geprekyukss_dashboard/static/src/app/dashboard/**/*.xml",
            "geprekyukss_dashboard/static/src/app/report/**/*.js",
            "geprekyukss_dashboard/static/src/app/report/**/*.xml",
            "geprekyukss_dashboard/static/src/scss/dashboard.scss",
            "geprekyukss_dashboard/static/src/scss/report.scss",
        ],
    },
    "installable": True,
    "application": True,
}
