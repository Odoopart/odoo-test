/** @odoo-module */

import {
    Component,
    onMounted,
    reactive,
    useEffect,
    useExternalListener,
    useRef,
    useState,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

// Komposisi item (Outlet, Self Order, Grabfood, Shopeefood, Gofood, Pengaturan)
// adalah revisi pemilik proyek atas daftar item di referensi desainnya — bukan
// daftar bawaan referensi, dan bukan pula menu bawaan Odoo.
//
// `route` = nama halaman yang BENAR-BENAR terdaftar di registry "pos_pages"
// Odoo 19 (lihat product_screen.js: `registry.category("pos_pages").add(...)`).
//
// `route: null` = item ini BELUM punya padanan di instance ini. Item tetap
// ditampilkan karena desain memintanya, TAPI kliknya tidak memindahkan pill
// aktif — hanya memberi tahu kasir bahwa saluran itu belum tersambung. Ini
// disengaja: kalau pill-nya ikut berpindah, layar akan berpura-pura sudah
// berpindah saluran padahal data produk & harganya belum ikut berubah.
//
// Untuk menyambungkan salah satu item, ada dua jalan:
//   1. isi `route` dengan nama halaman POS yang ada, atau
//   2. ganti isi cabang `if (!item.route)` di onMenuClick() dengan aksi nyata
//      (mis. memilih pricelist per saluran — proyek ini sudah punya data harga
//      per platform, jadi itu sambungan yang paling masuk akal).
/* ---------------------------------------------------------------------------
 * STATUS DRAWER (sidebar off-canvas di <992px)  — Fase E
 *
 * Ditaruh di tingkat MODUL, bukan di dalam komponen, karena DUA komponen
 * memakainya: GySidebar (panel yang digeser) dan GySidebarToggle (tombol di
 * topbar) — dan keduanya tidak punya hubungan induk/anak. Menitipkan status ini
 * ke objek `pos` akan mencampur data server dengan status tampilan.
 *
 * PENTING — kenapa dua komponen memakai `useState(gyDrawer)`, BUKAN `gyDrawer`
 * langsung. `reactive()` tingkat modul seperti ini TIDAK membuat komponen ikut
 * render. Di `owl.js` (web/static/lib/owl/owl.js) subscribenya diikat ke sebuah
 * CALLBACK, dan hanya `useState(state)` yang mengisinya dengan render komponen
 * (`return reactive(state, render)` di sana); `reactive(target)` tanpa callback
 * memakai `NO_CALLBACK`, jadi ia mencatat perubahan tapi tidak memberi tahu
 * siapa pun — nilai `gyDrawer.open` benar-benar berubah, sementara class
 * `gy-sidebar--open` dan `aria-expanded` tidak pernah ikut berubah. Ini bukan
 * teori: versi pertama Fase E memakai `this.drawer = gyDrawer` dan terukur
 * "klik masuk handler, tapi drawer tidak bergerak" (left tetap -264px,
 * aria-expanded tetap "false", tanpa satu pun error konsol).
 * `useState(gyDrawer)` membuat proxy BARU yang terikat ke render komponen yang
 * memanggilnya, sedangkan datanya tetap satu objek yang sama — jadi tombol di
 * topbar dan panelnya benar-benar berbagi status (lihat `reactive()`, jalur
 * `if (targets.has(target)) return reactive(targets.get(target), callback)`).
 * Menulis lewat proxy mana pun tetap memberi tahu SEMUA komponen yang membaca.
 * ------------------------------------------------------------------------- */
export const gyDrawer = reactive({ open: false });

// Elemen DOM yang menerima fokus kembali saat drawer ditutup (tombol pemicunya).
// SENGAJA bukan bagian dari state reaktif: ini node DOM, dan menaruh node di
// dalam state yang dipantau OWL berarti OWL memegang referensi ke elemen yang
// bisa sudah dilepas halaman.
let drawerTriggerEl = null;

export function setGyDrawerTrigger(el) {
    drawerTriggerEl = el;
}

/**
 * TUTUP drawer — satu-satunya jalan keluar drawer.
 *
 * Dipanggil dari empat tempat (Esc, klik backdrop, tombol x di dalam panel, dan
 * klik item menu). Dikumpulkan di satu fungsi supaya "kembalikan fokus ke tombol
 * pemicu" tidak pernah terlewat di salah satu jalan — syarat aksesibilitas yang
 * sudah disepakati ("fokus keyboard dikembalikan ke tombol hamburger setelah
 * menutup") — tanpa menyalin logika yang sama empat kali.
 *
 * Aman dipanggil saat drawer memang tertutup.
 */
export function closeGyDrawer() {
    if (!gyDrawer.open) {
        return;
    }
    gyDrawer.open = false;
    drawerTriggerEl?.focus();
}

const MENU_ITEMS = [
    { id: "outlet", label: "Outlet", icon: "fa-store", route: "ProductScreen" },
    { id: "self-order", label: "Self Order", icon: "fa-tablet", route: null },
    { id: "grabfood", label: "Grabfood", icon: "fa-motorcycle", route: null },
    { id: "shopeefood", label: "Shopeefood", icon: "fa-shopping-bag", route: null },
    { id: "gofood", label: "Gofood", icon: "fa-cutlery", route: null },
    { id: "settings", label: "Pengaturan", icon: "fa-cog", route: null },
];

/**
 * GySidebar — rel navigasi kiri tetap (240px) untuk POS.
 *
 * Komponen BARU: Odoo POS tidak punya rel seperti ini (hanya `Navbar` di atas).
 * Disisipkan ke akar aplikasi oleh `navbar/sidebar_patch.xml` (menambal
 * `point_of_sale.Chrome`) dan didaftarkan ke `Chrome.components` di
 * `overrides/models/models.js`. Tata letak 3 kolomnya murni CSS: `.pos`
 * dialihkan dari flex-column ke grid, lihat section 20 di `pos_theme.scss`.
 *
 * Juga menampung merek yang tadinya menempel di kiri navbar: logo `logo.jpg`
 * 34px + wordmark dua warna + tagline "AYAM GEPREK", semuanya dalam blok 44px.
 * Fase 1 sempat melepas gambar logonya mengikuti board pos2, tapi hasilnya di
 * layar kasir hanya tersisa kata "Geprek Yukss" tanpa lambang — jadi logo itu
 * dikembalikan 22 Sep 2026 dan sekarang dipakai di kedua brand (sidebar >=992px
 * dan navbar <992px) sekaligus sebagai favicon/logo POS: satu berkas merek.
 *
 * Sejak Fase E rel ini juga menjadi DRAWER di <992px: sebelumnya ia hanya
 * disembunyikan (`display: none`) sehingga Outlet/Self Order/Grabfood/
 * Shopeefood/Gofood/Pengaturan/Tutup Kasir sama sekali tidak bisa dijangkau
 * kasir di ponsel maupun tablet. Di <992px panelnya dibuat `position: fixed`
 * dan digeser keluar layar oleh section 23 pos_theme.scss; status buka/tutupnya
 * ada di `gyDrawer` (di atas) karena tombolnya hidup di komponen lain.
 */
export class GySidebar extends Component {
    static template = "geprekyukss_pos.GySidebar";
    static props = {};

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        this.state = useState({ activeId: "outlet" });
        // `useState`, bukan `gyDrawer` langsung — kalau tidak, perubahan status
        // drawer tidak pernah membuat komponen ini render (lihat kepala berkas).
        this.drawer = useState(gyDrawer);
        this.drawerRef = useRef("drawer");

        // Esc menutup drawer. Listener dipasang SEKALI, bukan hanya saat terbuka:
        // memasang/melepas listener setiap kali status berubah berarti ada dua
        // jalur yang keduanya harus benar, padahal handler-nya sendiri sudah
        // keluar lebih dulu kalau drawer memang sedang tertutup.
        useExternalListener(window, "keydown", this.onWindowKeydown);

        // Fokus dipindahkan KE DALAM drawer saat dibuka. Tanpa ini pengguna
        // keyboard tetap berada di tombol pemicu di belakang backdrop dan harus
        // menekan Tab berkali-kali untuk sampai ke menunya.
        useEffect(
            (open) => {
                if (open) {
                    this.drawerRef.el?.querySelector(".gy-nav-item")?.focus();
                }
            },
            () => [this.drawer.open]
        );
    }

    onWindowKeydown(ev) {
        if (ev.key === "Escape") {
            closeGyDrawer();
        }
    }

    // Klik di area gelap di belakang panel = jalan keluar yang paling sering
    // dipakai di ponsel. Sisanya (tombol x, Esc, tombol pemicu) ada di markup.
    onBackdropClick() {
        closeGyDrawer();
    }

    onCloseDrawer() {
        closeGyDrawer();
    }

    get menuItems() {
        return MENU_ITEMS.map((item) => ({
            ...item,
            active: item.id === this.state.activeId,
        }));
    }

    // CATATAN (overhaul tampilan): `cashierName` dan `cashierInitial` DIHAPUS
    // dari sini. Kartu kasir (avatar + nama) sudah tidak ada di sidebar: yang
    // tersisa di bawah hanya "Logout", dan nama kasir pindah ke kartu kasir
    // topbar. Getter yang tidak dipakai lagi adalah kode mati; kalau nanti
    // nama kasir dibutuhkan lagi di sidebar, ambil dari `this.pos.cashier.name`
    // di komponen yang memakainya, jangan menghidupkan kembali getter ini
    // tanpa pemakai.

    onMenuClick(item) {
        // Drawer ditutup LEBIH DULU, sebelum apa pun yang lain: di ponsel ia
        // menutupi seluruh layar, jadi notifikasi "belum dihubungkan" (item tanpa
        // halaman tujuan) akan muncul di belakang backdrop dan terbaca seperti
        // tombol yang tidak melakukan apa-apa.
        closeGyDrawer();
        if (!item.route) {
            this.notification.add(`${item.label} belum dihubungkan ke data POS.`, {
                type: "warning",
            });
            return;
        }
        this.state.activeId = item.id;
        this.pos.navigate(item.route);
    }

    onCloseRegister() {
        closeGyDrawer();
        this.pos.closeSession();
    }
}

/**
 * GySidebarToggle — tombol pemicu drawer di topbar (<992px).
 *
 * Kenapa komponen TERSENDIRI, bukan sekadar tombol di dalam tambalan template
 * navbar: `t-on-click` di dalam tambalan template dijalankan pada komponen yang
 * DITAMBAL (Navbar) — dan Navbar tidak punya metode kita, jadi tombolnya akan
 * diam saja saat diklik. Jadi tombolnya adalah komponen sendiri, didaftarkan ke
 * `Chrome.components` seperti GySidebar, lalu disisipkan oleh
 * `navbar/topbar_patch.xml`.
 *
 * Di >=992px tombolnya disembunyikan CSS (rel sidebar selalu terlihat), jadi
 * tidak perlu `t-if` lebar layar di sini.
 */
export class GySidebarToggle extends Component {
    static template = "geprekyukss_pos.GySidebarToggle";
    static props = {};

    setup() {
        // Sama seperti GySidebar: `useState` yang mengikat objek bersama ini ke
        // render komponen ini — `aria-expanded` ikut berubah dari sini.
        this.drawer = useState(gyDrawer);
        this.buttonRef = useRef("toggle");
        onMounted(() => setGyDrawerTrigger(this.buttonRef.el));
    }

    // Tombol yang sama membuka DAN menutup — di ponsel, menyentuh tombol yang
    // masih terlihat di bawah backdrop adalah cara termudah untuk kembali.
    onToggle() {
        if (gyDrawer.open) {
            closeGyDrawer();
        } else {
            gyDrawer.open = true;
        }
    }
}
