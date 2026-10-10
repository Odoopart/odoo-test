/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { Chrome } from "@point_of_sale/app/pos_app";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { GySidebar, GySidebarToggle } from "@geprekyukss_pos/app/navbar/sidebar";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { MemberCard } from "@geprekyukss_pos/app/screens/product_screen/member_card";
import { SpiceLevelPopup, SPICE_TEXT_LABELS } from "@geprekyukss_pos/app/screens/product_screen/spice_level_popup";
import { QuantityButtons } from "@point_of_sale/app/components/buttons/quantity_buttons/quantity_buttons";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

// Tambah getter di komponen Orderline (dipakai bareng layar kasir & struk)
// supaya template orderline_patch.xml bisa nampilin label level pedas dari kode
// "1".."5" yang tersimpan di field spice_level.
//
// Yang dipakai adalah label TEKS ("Level 3"), bukan emoji cabe: badge di panel
// order diminta teks saja, dan ikon `<i class="fa fa-fire">` yang dulu ada di
// markup badge sudah dihapus. Emoji tetap dipakai di popup pemilihan level.
patch(Orderline.prototype, {
    get spiceLevelLabel() {
        return SPICE_TEXT_LABELS[this.props.line.spice_level] || "";
    },
    gySetLineQuantity(line, qty) {
        if (qty <= 0) {
            line.order_id.removeOrderline(line);
        } else {
            line.setQuantity(qty);
        }
    },
    gyDeleteLine(line) {
        line.order_id.removeOrderline(line);
    },
});

// Daftarkan QuantityButtons sebagai sub-component Orderline (dipakai orderline_patch.xml)
patch(Orderline, {
    components: { ...Orderline.components, QuantityButtons },
});

// MemberCard dipakai di dalam template ProductScreen
// (product_screen_layout_patch.xml menyisipkan <MemberCard/> sebelum OrderSummary).
// Sebelumnya didaftarkan ke OrderDisplay padahal titik sisipnya tidak di sana,
// dan template member sebelumnya bahkan menargetkan `point_of_sale.OrderWidget`
// yang tidak ada di Odoo 19 — dua sebab kartu member tidak pernah dirender.
patch(ProductScreen, {
    components: { ...ProductScreen.components, MemberCard },
});

// GySidebar dipakai di dalam template akar aplikasi: sidebar_patch.xml menambal
// `point_of_sale.Chrome` dan menyisipkan <GySidebar/> sebelum <Navbar/>. Karena
// yang dirender adalah template milik Chrome, komponennya harus didaftarkan ke
// Chrome.components — sama polanya seperti MemberCard di atas.
//
patch(Chrome, {
    components: { ...Chrome.components, GySidebar },
});

// GySidebarToggle (tombol pemicu drawer di topbar, <992px) TIDAK boleh ikut di
// atas: yang dicari adalah <GySidebarToggle/> di dalam template
// `point_of_sale.Navbar`, dan OWL mencari definisi komponen di daftar komponen
// MILIK KOMPONEN YANG TEMPLATENYA SEDANG DIRENDER — jadi Navbar.components, bukan
// Chrome.components. Salah taruh = `OwlError: Cannot find the definition of
// component "GySidebarToggle"` yang menjatuhkan seluruh akar aplikasi POS, bukan
// cuma tombolnya menghilang (terukur 22 Sep 2026).
patch(Navbar, {
    components: { ...Navbar.components, GySidebarToggle },
});

// Spice level popup: titik hook resmi = ProductScreen.addProductToOrder
// (dipanggil saat kartu produk diklik). Versi ini meniru alur bawaan Odoo 19
// (lihat product_screen.js:426) lalu menambahkan spice_level ke vals orderline.
// CATATAN KOMPATIBILITAS: kalau nama method ini berubah saat upgrade Odoo,
// cek: grep -n "addProductToOrder" \
//   /usr/lib/python3/dist-packages/odoo/addons/point_of_sale/static/src/app/screens/product_screen/product_screen.js
patch(ProductScreen.prototype, {
    async addProductToOrder(product) {
        if (product && product.pos_spicy) {
            const spiceLevel = await new Promise((resolve) => {
                this.dialog.add(SpiceLevelPopup, {
                    productName: product.display_name,
                    getPayload: (value) => resolve(value),
                });
            });

            // Kasir batal pilih level -> jangan tambahkan produk ke order.
            if (!spiceLevel) {
                return;
            }

            const options = {};
            if (this.searchWord && product.isConfigurable()) {
                const searchWord = this.searchWord;
                const searchedProduct = product.product_variant_ids.filter(
                    (p) =>
                        (p.barcode && p.barcode.includes(searchWord)) ||
                        (p.default_code && p.default_code.includes(searchWord))
                );
                if (searchedProduct.length === 1) {
                    options["presetVariant"] = searchedProduct[0];
                }
            }

            const line = await this.pos.addLineToCurrentOrder(
                { product_tmpl_id: product, spice_level: spiceLevel },
                options
            );
            if (line) {
                this.showOptionalProductPopupIfNeeded(product);
            }
            return;
        }
        return super.addProductToOrder(product);
    },

    // Kode pendek order untuk judul panel ("Order #114").
    //
    // Sumbernya `order.floatingOrderName` MILIK ODOO (pos_order.js:
    // `floating_order_name || tracking_number`), bukan `order.name`. Diukur di DB
    // ini: `name` = "Restoran Mallengkeri - 034114" (panjang, memuat nama
    // konfigurasi) sedangkan `tracking_number` = "114" — yang kedua itulah yang
    // muat di panel 222px dan sepadan dengan "Order #A2" di board.
    // Fallback ke `name` hanya kalau order belum punya keduanya (order draft).
    get gyOrderCode() {
        const order = this.currentOrder;
        if (!order) {
            return "";
        }
        return order.floatingOrderName || order.name || "";
    },

    // Status order untuk pill di header panel. Diambil dari preset POS
    // (Dine In / Takeout / Delivery — terverifikasi ada di DB ini).
    // Sengaja KOSONG kalau preset tidak dipakai, supaya panel tidak menulis
    // "Dine In" pada order take away.
    get gyOrderMode() {
        return this.currentOrder?.preset_id?.name || "";
    },

    gyClearOrder() {
        const order = this.pos.getOrder();
        if (!order || order.isEmpty()) {
            return;
        }
        for (const line of [...order.lines]) {
            order.removeOrderline(line);
        }
    },

    // Baris "Tambah Catatan" di panel order.
    //
    // Dua kesalahan yang sudah diperbaiki di sini (keduanya terukur, bukan dugaan):
    //   1. `await import("@point_of_sale/...")` TIDAK ditransformasi oleh bundler aset
    //      produksi Odoo, sehingga browser menerima specifier mentah dan melempar
    //      "TypeError: Failed to resolve module specifier" — tombolnya gagal TOTAL
    //      walau 0 error saat memuat halaman. Harus impor STATIS di kepala berkas.
    //   2. Menulis `order.general_customer_note = ...` langsung melewatkan
    //      `order.setGeneralCustomerNote()` milik Odoo (pos_order.js:783) — metode
    //      yang dipakai tombol "Catatan" bawaan. Sekarang memakai metode itu.
    //
    // Catatan: tombol "Catatan" bawaan (ControlButtons) melakukan hal yang SAMA kalau
    // tidak ada baris terpilih. Jadi baris ini duplikat yang disengaja demi mengikuti
    // board; penggabungannya masuk Fase E (§9.4).
    async gyAddOrderNote() {
        const order = this.pos.getOrder();
        if (!order) {
            return;
        }
        const note = await makeAwaitable(this.dialog, TextInputPopup, {
            title: "Tambah Catatan",
            placeholder: "Tulis catatan untuk pesanan ini...",
            rows: 2,
            startingValue: order.general_customer_note || "",
        });
        if (typeof note === "string") {
            order.setGeneralCustomerNote(note);
        }
    },
});

// Penggabungan baris TIDAK boleh melintasi level pedas.
//
// Sejak checkbox "Group Products in POS" dicentang pada satuan PORSI/PAKET/GELAS/
// PCS (lihat scripts/perbaikan_17_gabung_baris_uom_pos.py), klik produk yang sama
// sudah benar menggabung jadi satu baris. Tapi `canBeMergedWith()` bawaan Odoo
// (point_of_sale/static/src/app/models/pos_order_line.js:325) membandingkan
// produk, harga, diskon, catatan, lot, dan `full_product_name` — TIDAK
// `spice_level`, karena field itu milik modul ini. Padahal `merge()` hanya
// menjumlahkan qty, sehingga level yang diminta belakangan HILANG.
//
// Terukur di harness browser (config 2, GEPREK ORIGINAL DADA/PAHA ATAS):
//   level 1 lalu level 5 -> 1 baris qty 2, badge tetap "1 \ud83c\udf36\ufe0f" (level 5 hilang)
// Setelah tambalan ini, dua baris dengan level berbeda tetap terpisah.
patch(PosOrderline.prototype, {
    canBeMergedWith(orderline) {
        if ((this.spice_level || "") !== (orderline.spice_level || "")) {
            return false;
        }
        return super.canBeMergedWith(orderline);
    },
});
