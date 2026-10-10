{
    "name": "Geprekyukss - Custom POS (Spice Level & Member WA)",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Level pedas per orderline + verifikasi member via nomor WhatsApp",
    "description": """
Custom module untuk POS Geprekyukss.
""",
    "author": "Custom - Geprekyukss",
    "depends": ["point_of_sale", "pos_restaurant"],
    "data": [
        "views/product_template_views.xml",
        "views/res_partner_views.xml",
        "views/pos_category_views.xml",
    ],
    "assets": {
        # Bundle POS. URUTAN PENTING untuk dua entri terakhir: Odoo menerapkan
        # tambalan template (blok "extensions") mengikuti urutan berkas di bundle,
        # jadi tambalan kita harus berada SETELAH berkas pos_restaurant yang
        # menambahkan .course-btn / .pay-order-button-restaurant. Karena itu
        # dipakai anchor ("after", <berkas pos_restaurant>, <berkas kita>).
        "point_of_sale._assets_pos": [
            "geprekyukss_pos/static/src/app/utils/fit_width_scale.js",
            "geprekyukss_pos/static/src/scss/pos_theme.scss",
            "geprekyukss_pos/static/src/overrides/components/category_selector/category_selector_patch.js",
            "geprekyukss_pos/static/src/overrides/components/category_selector/category_selector_patch.xml",
            "geprekyukss_pos/static/src/overrides/models/models.js",
            "geprekyukss_pos/static/src/app/screens/product_screen/spice_level_popup.js",
            "geprekyukss_pos/static/src/app/screens/product_screen/spice_level_popup.xml",
            "geprekyukss_pos/static/src/app/generic_components/orderline/orderline_patch.xml",
            "geprekyukss_pos/static/src/app/screens/product_screen/product_card_badges.xml",
            "geprekyukss_pos/static/src/app/navbar/header_brand_patch.xml",
            # Rel sidebar (Fase 2 "Overhaul POS Hijau"). sidebar_patch.xml menambal
            # point_of_sale.Chrome — tidak ada modul lain yang menambal template itu,
            # jadi tidak perlu anchor ("after", ...). Urutan sidebar.xml vs
            # sidebar_patch.xml tidak penting: Odoo mendaftarkan semua blok
            # "templates" lebih dulu, baru menerapkan blok "extensions".
            "geprekyukss_pos/static/src/app/navbar/sidebar.js",
            "geprekyukss_pos/static/src/app/navbar/sidebar.xml",
            "geprekyukss_pos/static/src/app/navbar/sidebar_patch.xml",
            # Topbar pos2 (Fase 2): judul halaman + kartu kasir (nama & status).
            # Kedua berkas ini menambal template yang JUGA ditambal modul lain —
            # point_of_sale.Navbar oleh pos_restaurant/pos_hr/pos_self_order, dan
            # point_of_sale.CashierName oleh pos_hr — TAPI anchor xpath-nya tidak
            # beririsan (mereka menyasar tombol Tables/Lock/DropdownItem dan
            # atribut t-on-click; kita menyasar `.navbar-menu` dan `img.avatar`).
            # Karena tidak beririsan, urutan berkas di bundle tidak mengubah
            # hasil, jadi tidak perlu anchor ("after", …).
            "geprekyukss_pos/static/src/app/navbar/topbar_patch.xml",
            "geprekyukss_pos/static/src/app/navbar/cashier_card_patch.xml",
            "geprekyukss_pos/static/src/app/screens/product_screen/product_screen_layout_patch.xml",
            "geprekyukss_pos/static/src/app/screens/product_screen/member_card.js",
            "geprekyukss_pos/static/src/app/screens/product_screen/member_card.xml",
            ("after", "pos_restaurant/static/src/app/screens/product_screen/actionpad_widget/actionpad_widget.xml", "geprekyukss_pos/static/src/app/screens/product_screen/actionpad_widget/actionpad_widget_patch.xml"),
            ("after", "pos_restaurant/static/src/app/screens/product_screen/control_buttons/control_buttons.xml", "geprekyukss_pos/static/src/app/screens/product_screen/control_buttons_patch.xml"),
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
