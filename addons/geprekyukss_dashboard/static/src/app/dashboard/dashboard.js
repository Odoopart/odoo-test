/** @odoo-module **/

import { Component, useState, useRef, useExternalListener, onWillStart, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { REPORTS } from "../report/reports_registry.js";

// ---------------------------------------------------------------
// FONT — mock High-Fidelity: Inter (UI) + JetBrains Mono (angka).
// Dimuat via <link>; CSS @import tidak reliable di bundle gabungan Odoo.
// ---------------------------------------------------------------
const FONT_URLS = [
    "https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,300;0,14..32,400;0,14..32,500;0,14..32,600;0,14..32,700;0,14..32,800;1,14..32,400&display=swap",
    "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap",
];

function loadFonts() {
    if (document.querySelector(`link[href="${FONT_URLS[0]}"]`)) return;
    const pre = document.createElement("link");
    pre.rel = "preconnect";
    pre.href = "https://fonts.googleapis.com";
    document.head.appendChild(pre);
    const pre2 = document.createElement("link");
    pre2.rel = "preconnect";
    pre2.href = "https://fonts.gstatic.com";
    pre2.crossOrigin = "";
    document.head.appendChild(pre2);
    for (const href of FONT_URLS) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        document.head.appendChild(link);
    }
}

// ---------------------------------------------------------------
// NAVIGASI — 8 item, struktur & urutan sama dengan sidebar mock.
// 7 item = tab dashboard, 1 item terakhir = halaman Laporan (report shell).
// ---------------------------------------------------------------
const NAV_ITEMS = [
    // eyebrow = teks kecil di atas konten (mock: "RINGKASAN KINERJA · SEMUA OUTLET")
    { id: "beranda", label: "Beranda", icon: "fa-home", note: "Ringkasan kinerja", eyebrow: "Ringkasan Kinerja" },
    { id: "laporan", label: "Laporan", icon: "fa-file-text-o", note: "Laba rugi & neraca" },
    { id: "penjualan", label: "Penjualan", icon: "fa-shopping-cart", note: "Transaksi & channel" },
    { id: "hpp", label: "Biaya & HPP", icon: "fa-cutlery", note: "HPP & beban usaha" },
    { id: "kas", label: "Kas & Bank", icon: "fa-university", note: "Saldo & posisi kas" },
    { id: "aset", label: "Aset", icon: "fa-building-o", note: "Aset tetap & penyusutan" },
    { id: "persediaan", label: "Persediaan", icon: "fa-cubes", note: "Nilai stok & waste" },
    { id: "pajak", label: "Pajak (PBJT)", icon: "fa-percent", note: "PBJT & rekonsiliasi Bapenda", eyebrow: "Pajak Daerah" },
];

// Item sidebar terakhir (mock) — membuka report shell, bukan tab.
const NAV_REPORTS = {
    id: "lapkeu",
    label: "Laporan Keuangan Lengkap",
    icon: "fa-line-chart",
    note: "AFR & MIS Builder",
};

// Alias kompatibilitas untuk referensi lama.
const TABS = NAV_ITEMS;

// ---------------------------------------------------------------
// DATA DEMO — HANYA untuk bagian yang belum punya sumber data di backend
// (panel kepatuhan PSAK & log audit trail). Setiap tampilan yang memakai
// konstanta di bawah WAJIB diberi badge "data demo" di template.
// ---------------------------------------------------------------
const DEMO_PSAK = {
    pass: [
        { label: "Double-entry & trial balance", note: "Odoo auto-reconcile" },
        { label: "Basis akrual", note: "Konfigurasi Odoo aktif" },
        { label: "FIFO real-time (Persediaan)", note: "Stock Valuation module" },
        { label: "Audit trail jurnal", note: "Log entry lengkap & terkunci" },
        { label: "Rekonsiliasi bank & e-wallet", note: "Saldo buku cocok" },
    ],
    review: [
        { label: "PPN — DPP nilai lain", note: "Verifikasi rate aktif di Odoo" },
        { label: "Gift Card / eWallet / Uang Muka", note: "Klasifikasi liabilitas vs revenue" },
        { label: "Tips karyawan", note: "Revenue vs pass-through" },
        { label: "Klasifikasi settlement QRIS", note: "Piutang vs kas?" },
        { label: "Principal vs Agent (Delivery)", note: "Gross vs net revenue" },
    ],
    pending: [
        { label: "Laporan FY penuh (tutup buku)", note: "Periode belum ditutup" },
        { label: "Register Aset PSAK 16", note: "Komponen aset per item" },
        { label: "Akrual PPh 21 & PPh Badan", note: "Estimasi kewajiban pajak" },
        { label: "PSAK 73 — Sewa Operasi", note: "Mapping lease restoran" },
        { label: "Laporan Perubahan Ekuitas", note: "Belum disusun" },
        { label: "CALK (Catatan Lap. Keuangan)", note: "Diperlukan untuk PSAK full" },
    ],
};

const DEMO_AUDIT = [
    { time: "12 Sep 2026 · 14:32", user: "admin@geprekyukss", kind: "pass", action: "Rekonsiliasi bank — konfirmasi saldo buku" },
    { time: "12 Sep 2026 · 11:15", user: "finance@geprekyukss", kind: "pass", action: "Posting jurnal HPP periode berjalan — FIFO" },
    { time: "11 Sep 2026 · 09:44", user: "admin@geprekyukss", kind: "review", action: "Settlement QRIS — klasifikasi pending" },
    { time: "10 Sep 2026 · 16:20", user: "finance@geprekyukss", kind: "pass", action: "Rekonsiliasi bank selesai — selisih Rp0,00" },
    { time: "08 Sep 2026 · 13:05", user: "admin@geprekyukss", kind: "review", action: "Akrual PPh 21 — pending konfirmasi rate efektif" },
    { time: "05 Sep 2026 · 08:30", user: "system", kind: "info", action: "Auto-close periode — Odoo Accounting" },
];

// Fallback kartu kas/bank bila finance.cash_positions kosong (mis. periode
// tanpa mutasi). Tren/posisi nyata memakai data GL begitu tersedia.
// Nilai dalam RUPIAH MENTAH (bukan juta) agar konsisten dengan payload GL
// dan formatRp(). 23.020.000 → "Rp 23,0 jt".
const DEMO_CASH_CARDS = [
    { label: "BNI", val: 23_020_000, status: "pass", note: "Rekonsiliasi selesai" },
    { label: "BSI", val: 157_300_000, status: "pass", note: "Rekonsiliasi selesai" },
    { label: "QRIS / Piutang Settle.", val: 80_600_000, status: "review", note: "Settlement belum diklasifikasi" },
    { label: "Kas Operasional Resto", val: null, status: "review", note: "Perlu rekonsiliasi manual" },
];

// ---------------------------------------------------------------
// IKON SVG (mock memakai line-icon, bukan FontAwesome)
// markup() wajib: nilai dikirim ke template lewat t-out agar dirender
// sebagai HTML, bukan teks yang di-escape.
// ---------------------------------------------------------------
// aria-hidden + focusable=false: ikon selalu dekoratif (teksnya ada di sebelah
// atau di aria-label tombolnya) — tanpa ini screen reader membacakan SVG kosong.
const svg = (body, extra = "") =>
    markup(
        `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
            `stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" ` +
            `aria-hidden="true" focusable="false" ${extra}>${body}</svg>`,
    );

const ICONS = {
    revenue: svg('<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>'),
    hpp: svg('<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>'),
    gross: svg('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>'),
    opex: svg('<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'),
    profit: svg('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'),
    cash: svg('<rect x="3" y="10" width="18" height="11" rx="1"/><path d="M7 10V7a5 5 0 0 1 10 0v3"/>'),
    bank: svg('<line x1="3" y1="21" x2="21" y2="21"/><path d="M5 21V10l7-6 7 6v11"/><line x1="9" y1="21" x2="9" y2="13"/><line x1="15" y1="21" x2="15" y2="13"/>'),
    cart: svg('<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 1.95-1.57l1.65-7.43H6"/>'),
    box: svg('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/>'),
    building: svg('<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>'),
    clock: svg('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    wallet: svg('<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>'),
    calendar: svg('<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>', 'width="12" height="12"'),
    home: svg('<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>', 'width="12" height="12"'),
    download: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>', 'width="12" height="12" stroke-width="2.5"'),
};

// Brandmark topnav (mock: 4 kotak rounded) — dipakai juga oleh report shell,
// karena itu di-export (bukan konstanta modul privat).
export const BRANDMARK = markup(
    '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2">' +
        '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>' +
        '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
);

const MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
];
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const MAX_RANGE_DAYS = 366;

// ---------------------------------------------------------------
// PALET & DEFAULTS CHART (token mock High-Fidelity)
// Satu sumber warna: SCSS memakai nilai yang sama persis.
// ---------------------------------------------------------------
const MONO = "'JetBrains Mono', ui-monospace, monospace";
const SANS = "'Inter', system-ui, sans-serif";

const C = {
    navy950: "#05101f", navy900: "#091628", navy800: "#0e1e38", navy750: "#132548",
    navy700: "#1a2f5a", navy600: "#243f78", navy500: "#2f5096", navy400: "#4370bb",
    navy300: "#6b93d0", navy200: "#a8c1e5", navy100: "#dce8f5", navy50: "#eef4fb",
    teal800: "#0c6560", teal700: "#0e7c76", teal600: "#0d9488", teal500: "#14b8a6",
    teal400: "#2dd4bf", teal200: "#99f6e4", teal100: "#ccfbf1", teal50: "#f0fdfa",
    emerald700: "#047857", emerald600: "#059669", emerald500: "#10b981", emerald400: "#34d399",
    amber700: "#b45309", amber600: "#d97706", amber500: "#f59e0b", amber400: "#fbbf24",
    red700: "#b91c1c", red600: "#dc2626", red500: "#ef4444",
    slate900: "#0f172a", slate800: "#1e293b", slate700: "#334155", slate600: "#475569",
    slate500: "#64748b", slate400: "#94a3b8", slate300: "#cbd5e1", slate200: "#e2e8f0",
    slate100: "#f1f5f9", slate50: "#f8fafc",
};

// Warna seri per makna (mock)
const PALETTE = {
    revenue: C.navy800,     // bar pendapatan
    cost: C.navy200,        // bar biaya/HPP
    gross: C.teal600,       // garis laba kotor
    profit: C.emerald500,   // garis laba bersih
    positive: C.emerald600, // waterfall naik
    negative: C.red600,     // waterfall turun
    net: C.navy900,         // waterfall total
    outletA: C.navy900,
    outletB: C.navy500,
};

// Seri kategorikal generik (tab lama + kategori produk/channel/pembayaran)
// Urutan index dipertahankan: dipakai gkKategoriColor/gkExpenseColor/dll.
const CHART_COLORS = [C.teal600, C.amber500, C.navy400, C.red600, C.navy900, C.slate400];

/**
 * Default global Chart.js — dipanggil sekali per renderCharts().
 * Tujuannya: SELURUH chart (termasuk renderer lama) langsung konsisten
 * dengan mock (tooltip navy, tick mono 10px, grid slate-200, border mati)
 * tanpa perlu menyetel opsi satu per satu.
 */
function applyChartDefaults(Chart) {
    Chart.defaults.font.family = MONO;
    Chart.defaults.font.size = 10;
    Chart.defaults.color = C.slate500;
    Chart.defaults.borderColor = C.slate200;
    const tip = Chart.defaults.plugins.tooltip;
    tip.backgroundColor = C.navy900;
    tip.borderColor = C.navy750;
    tip.borderWidth = 1;
    tip.titleColor = C.teal400;
    tip.bodyColor = "#ffffff";
    tip.titleFont = { family: MONO, size: 11, weight: "600" };
    tip.bodyFont = { family: MONO, size: 11 };
    tip.padding = 12;
    tip.cornerRadius = 12;
    tip.boxPadding = 4;
}

// OVERHAUL 15 Sep: const GAUGE dihapus — gauge "Status Keuangan" tidak lagi dipakai (K1).

export function formatRp(v, compact = false) {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    if (compact) {
        // Gaya mock: "Rp983,48 jt" — 2 desimal, tanpa spasi setelah "Rp".
        if (Math.abs(n) >= 1e9) return `Rp${(n / 1e9).toFixed(2).replace(".", ",")} M`;
        if (Math.abs(n) >= 1e6) return `Rp${(n / 1e6).toFixed(2).replace(".", ",")} jt`;
        if (Math.abs(n) >= 1e3) return `Rp${(n / 1e3).toFixed(0)} rb`;
    }
    return "Rp " + n.toLocaleString("id-ID", { maximumFractionDigits: 0 });
}

/** Nilai bertanda (+/−) dalam juta rupiah — untuk baris arus kas. */
export function formatSigned(v) {
    const n = Number(v || 0);
    return `${n >= 0 ? "+" : "−"}Rp${(Math.abs(n) / 1e6).toFixed(2).replace(".", ",")} jt`;
}

/** Persentase gaya Indonesia (+12,4% / −3,2%). */
export function formatPct(v, dec = 1) {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    return `${n < 0 ? "−" : ""}${Math.abs(n).toFixed(dec).replace(".", ",")}%`;
}

export class GkDashboard extends Component {
    static template = "geprekyukss_dashboard.Main";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            activeTab: "beranda",
            // Shell mock: sidebar off-canvas < 1024px (hamburger di topnav)
            sidebarOpen: false,
            // Overlay: null | "audit" (modal Audit Trail di footer Beranda)
            modal: null,
            // Tab aktif di kartu Arus Kas (PSAK 2 metode tak langsung)
            cfTab: "operasi",
            // SPEC_OVERHAUL F0: date range — default "month" pill, toggle to custom.
            // Default = Agustus 2026 (bulan data pertama — konsisten dgn data existing).
            rangeMode: "month",
            activeYear: 2026,
            activeMonth: 8,        // 8 = Agustus
            date_from: "2026-08-01",
            date_to: "2026-08-31",
            rangeError: "",
            activePreset: "",
            loading: false,
            // F5: tombol topbar XLSX sedang menyiapkan ekspor (menahan klik ganda)
            exporting: false,
            data: null,
            charts: [],
            outletFilter: { id: "all", name: "Semua Outlet", ids: [] },
            availableOutlets: [{ id: "all", name: "Semua Outlet", ids: [] }],
            outletMenuOpen: false,
            lastUpdated: null,
        });
        this.tabs = TABS;
        this.months = MONTHS;
        this.reports = REPORTS;
        this.mainRef = useRef("main");
        this.outletWrapRef = useRef("outletWrap");
        this.formatRp = formatRp;
        this.formatSigned = formatSigned;
        this.formatPct = formatPct;
        this.brandmark = BRANDMARK;
        this.icons = ICONS;
        this.modalRef = useRef("modalRef");
        onWillStart(() => loadFonts());
        useExternalListener(window, "click", (ev) => {
            const wrap = this.outletWrapRef.el;
            if (wrap && !wrap.contains(ev.target)) {
                this.state.outletMenuOpen = false;
            }
        });
        // A11Y (Fase 5): Escape menutup modal audit trail / dropdown outlet —
        // perilaku wajib untuk role="dialog" & aria-haspopup.
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key !== "Escape") return;
            if (this.state.modal) {
                this.closeModal();
            } else if (this.state.outletMenuOpen) {
                this.state.outletMenuOpen = false;
            }
        });
        this.loadAvailableOutlets();
        this.load();
    }

    // ---- shell helpers (topnav + sidebar mock) ----
    /** Item sidebar dashboard (7 tab) + entri terakhir ke halaman Laporan. */
    get navItems() {
        return [...NAV_ITEMS, NAV_REPORTS];
    }

    /** Label tab aktif — dipakai eyebrow row di dalam .gk-main. */
    get activeTabLabel() {
        const item = this.navItems.find((t) => t.id === this.state.activeTab);
        return item ? item.label : "";
    }

    /** Catatan kecil di kanan eyebrow (mock: "20 Jun – 31 Agu 2026"). */
    get activeTabNote() {
        const item = NAV_ITEMS.find((t) => t.id === this.state.activeTab);
        return item ? item.note : "";
    }

    /** Teks eyebrow (mock: "RINGKASAN KINERJA · SEMUA OUTLET"). */
    get eyebrowText() {
        const item = NAV_ITEMS.find((t) => t.id === this.state.activeTab);
        const base = (item && item.eyebrow) || this.activeTabLabel;
        return `${base} · ${this.state.outletFilter.name}`.toUpperCase();
    }

    // --- F2 (audit GUI 26 Sep): transparansi cakupan filter outlet ---
    /** True bila filter outlet aktif (bukan "Semua Outlet"). */
    get outletFilterActive() {
        const f = this.state.outletFilter;
        return !!(f && f.ids && f.ids.length);
    }

    /**
     * Tab yang KPI & laporannya bersumber dari GL konsolidasi (bukan POS
     * per-outlet) — TIDAK ikut ter-filter saat filter outlet aktif. Dipakai
     * untuk memberi label eksplisit agar user tidak menyimpulkan seluruh
     * dashboard mengikuti outlet (audit GUI F2).
     */
    get tabIsConsolidated() {
        return ["beranda", "laporan", "hpp", "kas", "aset", "persediaan"]
            .includes(this.state.activeTab);
    }

    /** Estimasi kontribusi outlet (POS-based) — ada hanya saat filter outlet aktif. */
    get outletContribution() {
        return (this.state.data && this.state.data.outlet_contribution) || null;
    }

    /** Klik item sidebar: tab dashboard, atau halaman Laporan (report shell). */
    onNavClick(item) {
        if (item.id === NAV_REPORTS.id) {
            this.closeSidebar();
            this.openReports();
            return;
        }
        this.selectTab(item.id);
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
    }

    // ---- header helpers ----
    get rangeLabel() {
        if (this.state.rangeError) return "Rentang tidak valid";
        if (!this.state.date_from || !this.state.date_to) return "Pilih rentang";
        return `${this.formatShort(this.state.date_from)} – ${this.formatShort(this.state.date_to)}`;
    }

    formatShort(iso) {
        const [y, m, d] = (iso || "").split("-").map(Number);
        if (!y || !m || !d) return iso || "…";
        return `${d} ${MONTHS_SHORT[m - 1]} ${y}`;
    }

    _monthPeriod(y, m) {
        const lastDay = new Date(y, m, 0).getDate();
        return {
            date_from: `${y}-${String(m).padStart(2, "0")}-01`,
            date_to: `${y}-${String(m).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`,
        };
    }

    get lastUpdatedLabel() {
        if (!this.state.lastUpdated) return "—";
        const d = this.state.lastUpdated;
        return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    }

    get period() {
        // SPEC_OVERHAUL F0: month mode → turun dari activeYear/Month; custom → apa adanya
        if (this.state.rangeMode === "custom") {
            return { date_from: this.state.date_from || "", date_to: this.state.date_to || "" };
        }
        return this._monthPeriod(this.state.activeYear, this.state.activeMonth);
    }

    get monthLabel() {
        // F0: label pill di mode month = "Agustus 2026"; di mode custom = range
        if (this.state.rangeMode === "custom") {
            return this.rangeLabel;
        }
        return `${this.months[this.state.activeMonth - 1]} ${this.state.activeYear}`;
    }

    async load() {
        if (this.state.rangeMode === "month") {
            // Sync date_from/date_to dgn bulan aktif (kalau ada perubahan via prev/next)
            const p = this._monthPeriod(this.state.activeYear, this.state.activeMonth);
            this.state.date_from = p.date_from;
            this.state.date_to = p.date_to;
        }
        if (!this.state.date_from || !this.state.date_to) return;
        if (this.state.rangeError) return;
        this.state.loading = true;
        this.destroyCharts();
        try {
            this.state.data = await this.orm.call(
                "geprekyukss.dashboard.data",
                "get_dashboard_data",
                [this.period.date_from, this.period.date_to, this.state.outletFilter.ids],
            );
            this.state.lastUpdated = new Date();
        } catch (e) {
            console.error("dashboard load failed", e);
            this.state.data = { has_data: false, summary: null, finance: null, sales: null, ops: null };
        } finally {
            this.state.loading = false;
        }
        setTimeout(() => this.renderCharts(), 50);
    }

    async loadAvailableOutlets() {
        try {
            const rows = await this.orm.call(
                "geprekyukss.dashboard.data",
                "list_available_outlets",
                [],
            );
            const all = { id: "all", name: "Semua Outlet", ids: [] };
            this.state.availableOutlets = [
                all,
                ...rows.map((r) => ({ id: r.id, name: r.name, ids: [r.id] })),
            ];
        } catch (e) {
            console.warn("list_available_outlets failed; pakai default", e);
        }
    }

    // ---- date range handlers (F0 foundation, referensi: 1 Jan – 31 Jan 2025 ▼) ----
    setRangeMode(mode) {
        if (this.state.rangeMode === mode) return;
        this.state.rangeError = "";
        if (mode === "custom") {
            // Prefill dari bulan aktif → user bisa geser manual
            const p = this._monthPeriod(this.state.activeYear, this.state.activeMonth);
            this.state.date_from = p.date_from;
            this.state.date_to = p.date_to;
            this.state.activePreset = "";
            this.state.rangeMode = "custom";
        } else {
            // kembali ke mode bulan: pastikan date_from/date_to sinkron dgn bulan
            const p = this._monthPeriod(this.state.activeYear, this.state.activeMonth);
            this.state.date_from = p.date_from;
            this.state.date_to = p.date_to;
            this.state.activePreset = "";
            this.state.rangeMode = "month";
        }
        this.load();
    }

    onCustomRangeChange() {
        // Triggered saat input date di mode custom berubah
        const f = this.state.date_from, t = this.state.date_to;
        this.state.activePreset = "";
        if (!f || !t) {
            this.state.rangeError = "";
            return;
        }
        if (f > t) {
            this.state.rangeError = "Tanggal awal melebihi tanggal akhir.";
            return;
        }
        const days = (new Date(t) - new Date(f)) / 86400000;
        if (days > MAX_RANGE_DAYS) {
            this.state.rangeError = "Rentang maksimal 1 tahun.";
            return;
        }
        this.state.rangeError = "";
        this.load();
    }

    applyPreset(key) {
        const today = new Date();
        const iso = (d) =>
            `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        let f, t;
        if (key === "today") {
            f = today; t = today;
        } else if (key === "7d") {
            t = today; f = new Date(today); f.setDate(f.getDate() - 6);
        } else if (key === "30d") {
            t = today; f = new Date(today); f.setDate(f.getDate() - 29);
        } else if (key === "month_current") {
            f = new Date(today.getFullYear(), today.getMonth(), 1);
            t = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        } else if (key === "month_prev") {
            f = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            t = new Date(today.getFullYear(), today.getMonth(), 0);
        } else if (key === "ytd") {
            f = new Date(today.getFullYear(), 0, 1); t = today;
        }
        if (!f || !t) return;
        // preset selalu mengisi tanggal & berpindah ke mode custom
        this.state.date_from = iso(f);
        this.state.date_to = iso(t);
        this.state.activePreset = key;
        this.state.rangeMode = "custom";
        this.state.rangeError = "";
        this.load();
    }

    // month mode → prev/next nav (referensi: ‹ pill ›)
    prevMonth() {
        if (this.state.rangeMode === "custom") {
            this.setRangeMode("month");
            return;
        }
        let m = this.state.activeMonth - 1, y = this.state.activeYear;
        if (m < 1) { m = 12; y -= 1; }
        this.state.activeMonth = m; this.state.activeYear = y;
        this.load();
        this.scrollTop();
    }

    nextMonth() {
        if (this.state.rangeMode === "custom") {
            this.setRangeMode("month");
            return;
        }
        let m = this.state.activeMonth + 1, y = this.state.activeYear;
        if (m > 12) { m = 1; y += 1; }
        this.state.activeMonth = m; this.state.activeYear = y;
        this.load();
        this.scrollTop();
    }

    destroyCharts() {
        for (const c of this.state.charts) {
            try { c.destroy(); } catch (_) {}
        }
        this.state.charts = [];
    }

    CHART_COLOR(idx) { return CHART_COLORS[idx % CHART_COLORS.length]; }

    async renderCharts() {
        const d = this.state.data;
        if (!d || !d.has_data) return;
        await loadBundle("web.chartjs_lib");
        const Chart = window.Chart;
        if (!Chart) return;
        applyChartDefaults(Chart);
        this.destroyCharts();
        if (this.state.activeTab === "beranda") {
            this.renderBerandaMonthly(Chart);
            this.renderBerandaOutlet(Chart);
            this.renderBerandaKategori(Chart);
            this.renderWaterfall(Chart);
        } else if (this.state.activeTab === "laporan" && d.summary) {
            this.renderLineDaily(Chart, d.summary.daily || []);
        } else if (this.state.activeTab === "penjualan" && d.sales) {
            this.renderDonutChannels(Chart, d.sales.channels || []);
        } else if (this.state.activeTab === "hpp" && d.finance) {
            if (d.summary) this.renderLineDaily(Chart, d.summary.daily || []);
        }
    }

    /**
     * Tren Kinerja Bulanan (mock: bar + line).
     * Bar = pendapatan & biaya per bulan, garis = laba bersih bulanan.
     * Sumber: beranda.laba_bulanan (agregasi GL via compute MIS).
     */
    renderBerandaMonthly(Chart) {
        const el = document.querySelector(".gk-chart-monthly canvas");
        if (!el) return;
        const rows = this.monthlyRows();
        if (!rows.length) return;
        this.state.charts.push(new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.label),
                datasets: [
                    { type: "bar", label: "Net Revenue", data: rows.map((r) => r.income || 0), backgroundColor: PALETTE.revenue, borderRadius: 4, barPercentage: 0.7 },
                    { type: "bar", label: "Total Biaya", data: rows.map((r) => r.expense || 0), backgroundColor: PALETTE.cost, borderRadius: 4, barPercentage: 0.7 },
                    {
                        type: "line", label: "Laba Bersih", data: rows.map((r) => r.value || 0),
                        borderColor: PALETTE.gross, backgroundColor: PALETTE.gross, borderWidth: 2.5,
                        tension: 0.35, pointRadius: 4, pointHoverRadius: 6,
                        pointBackgroundColor: PALETTE.gross, pointBorderColor: "#fff", pointBorderWidth: 2,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 16, color: C.slate500 } },
                    tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${formatRp(c.parsed.y, true)}` } },
                },
                scales: {
                    y: {
                        grid: { color: C.slate200, drawTicks: false },
                        border: { display: false },
                        ticks: { color: C.slate500, callback: (v) => `${Math.round(v / 1e6)} jt` },
                    },
                    x: { grid: { display: false }, border: { display: false }, ticks: { color: C.slate500, maxRotation: 0 } },
                },
            },
        }));
    }

    /** Revenue per Outlet — bar horizontal (mock). */
    renderBerandaOutlet(Chart) {
        const el = document.querySelector(".gk-chart-outlet canvas");
        if (!el) return;
        const rows = this.outletBars();
        if (!rows.length) return;
        this.state.charts.push(new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.outlet),
                datasets: [{
                    label: "Net Revenue",
                    data: rows.map((r) => r.revenue),
                    backgroundColor: rows.map((_, i) => (i === 0 ? PALETTE.outletA : PALETTE.outletB)),
                    borderRadius: 4,
                    barThickness: 32,
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => formatRp(c.parsed.x, true) } } },
                scales: {
                    x: {
                        grid: { color: C.slate200, drawTicks: false },
                        border: { display: false },
                        ticks: { color: C.slate500, callback: (v) => `${Math.round(v / 1e6)} jt` },
                    },
                    y: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: { color: C.slate700, font: { family: MONO, size: 11 } },
                    },
                },
            },
        }));
    }

    /**
     * Waterfall arus kas (mock) — Chart.js floating bar: tiap baris digambar
     * dari posisi saldo berjalan (base) setinggi perubahan (span). Bar terakhir
     * = total neto berwarna navy.
     */
    renderWaterfall(Chart) {
        const el = document.querySelector(".gk-chart-waterfall canvas");
        if (!el) return;
        const rows = this.cfRows();
        if (!rows.length) return;
        let running = 0;
        const steps = rows.map((r) => {
            const start = running;
            running += r.val;
            return {
                label: r.label,
                val: r.val,
                span: [Math.min(start, running), Math.max(start, running)],
                net: false,
            };
        });
        const total = running;
        steps.push({
            label: this.cfTotalLabel(),
            val: total,
            span: [Math.min(0, total), Math.max(0, total)],
            net: true,
        });
        this.state.charts.push(new Chart(el, {
            type: "bar",
            data: {
                labels: steps.map((s) => s.label),
                datasets: [{
                    data: steps.map((s) => s.span),
                    backgroundColor: steps.map((s) =>
                        s.net ? PALETTE.net : s.val >= 0 ? PALETTE.positive : PALETTE.negative),
                    borderRadius: 3,
                    barThickness: 28,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (c) => formatSigned(steps[c.dataIndex].val),
                        },
                    },
                },
                scales: {
                    y: {
                        grid: { color: C.slate200, drawTicks: false },
                        border: { display: false },
                        ticks: { color: C.slate500, callback: (v) => `${Math.round(v / 1e6)} jt` },
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: { color: C.slate500, maxRotation: 0, autoSkip: false, font: { family: MONO, size: 9 } },
                    },
                },
            },
        }));
    }

    // K3b-rev 15 Sep: donut Beranda = 5 kategori produk (category_map.json).
    // Warna dikunci per kategori — urutan = CHART_COLORS.
    gkKategoriColor(name) {
        const MAP = {
            "Ayam Geprek": CHART_COLORS[0],
            "Paket Hemat": CHART_COLORS[1],
            "Snack & Tambahan": CHART_COLORS[2],
            "Minuman": CHART_COLORS[3],
            "Lainnya": CHART_COLORS[5],
        };
        return MAP[name] || CHART_COLORS[5];
    }

    /**
     * Donut kategori produk (mock: Distribusi Channel / kategori).
     * Sumber = beranda.kategori_produk (category_map.json); bila kosong,
     * jatuh ke komposisi channel penjualan supaya kartu tidak kosong.
     */
    renderBerandaKategori(Chart) {
        const el = document.querySelector(".gk-chart-kategori canvas");
        if (!el) return;
        const kat = this.kategori();
        const cat = kat.length
            ? kat.map((c) => ({ name: c.name, amount: c.amount, color: c.color }))
            : this.channels().map((c) => ({ name: c.name, amount: c.amount, color: c.color }));
        if (!cat.length) return;
        const total = cat.reduce((s, c) => s + c.amount, 0);
        this.state.charts.push(new Chart(el, {
            type: "doughnut",
            data: {
                labels: cat.map((c) => c.name),
                datasets: [{
                    data: cat.map((c) => c.amount),
                    backgroundColor: cat.map((c) => c.color),
                    borderWidth: 2,
                    borderColor: "#fff",
                    hoverOffset: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: { legend: { display: false } },
            },
            plugins: [{
                id: "gkDonutCenter",
                afterDraw(chart) {
                    const ctx = chart.ctx;
                    const meta = chart.getDatasetMeta(0);
                    if (!meta.data.length) return;
                    const { x, y } = meta.data[0];
                    ctx.save();
                    ctx.textAlign = "center";
                    ctx.font = `800 15px ${MONO}`;
                    ctx.fillStyle = C.navy900;
                    ctx.fillText(formatRp(total, true), x, y - 1);
                    ctx.font = `10px ${MONO}`;
                    ctx.fillStyle = C.slate400;
                    ctx.fillText("Total", x, y + 14);
                    ctx.restore();
                },
            }],
        }));
    }

    renderLineDaily(Chart, daily) {
        const el = document.querySelector(".gk-chart-daily canvas");
        if (!el) return;
        const labels = daily.map(x => x.date.slice(8));
        const values = daily.map(x => x.amount);
        const maxV = Math.max(...values, 1);
        const ctx = el.getContext("2d");
        const h = (el.parentElement && el.parentElement.clientHeight) || 300;
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, "rgba(13, 148, 136, 0.18)");
        gradient.addColorStop(1, "rgba(13, 148, 136, 0)");
        let maxIdx = -1, minIdx = -1;
        values.forEach((v, i) => {
            if (maxIdx < 0 || v > values[maxIdx]) maxIdx = i;
            if (minIdx < 0 || v < values[minIdx]) minIdx = i;
        });
        const avg = values.reduce((s, v) => s + v, 0) / Math.max(values.length, 1);
        this.state.charts.push(new Chart(el, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Omzet Harian",
                        data: values,
                        borderColor: C.teal600,
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 2,
                        pointHoverRadius: 4,
                        order: 1,
                    },
                    {
                        label: "Rata-rata Harian",
                        data: labels.map(() => avg),
                        borderColor: "rgba(100, 116, 139, 0.55)",
                        borderDash: [5, 5],
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false,
                        order: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        filter: (item) => item.datasetIndex === 0,
                        callbacks: { label: (c) => formatRp(c.parsed.y) },
                    },
                },
                scales: {
                    y: {
                        grid: { color: C.slate200, drawTicks: false },
                        border: { display: false },
                        ticks: {
                            color: C.slate500,
                            callback: (v) => (v >= 1e6 ? `Rp ${Math.round(v / 1e6)} jt` : formatRp(v, true)),
                        },
                        suggestedMax: maxV * 1.15,
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: { color: C.slate500 },
                    },
                },
            },
            plugins: [{
                id: "gkHighLow",
                afterDatasetsDraw(chart) {
                    const cctx = chart.ctx;
                    const meta = chart.getDatasetMeta(0);
                    const area = chart.chartArea;
                    if (!meta || !meta.data || !area) return;
                    const drawTag = (idx, dotColor) => {
                        const pt = meta.data[idx];
                        if (!pt) return;
                        const val = formatRp(values[idx], true);
                        cctx.save();
                        cctx.fillStyle = dotColor;
                        cctx.beginPath();
                        cctx.arc(pt.x, pt.y, 3, 0, Math.PI * 2);
                        cctx.fill();
                        cctx.strokeStyle = "#fff";
                        cctx.lineWidth = 1.5;
                        cctx.stroke();
                        cctx.font = "600 11px 'Inter', 'Segoe UI', sans-serif";
                        const w = cctx.measureText(val).width;
                        let tx = Math.min(Math.max(pt.x - w / 2 - 5, area.left), area.right - w - 10);
                        let ty = pt.y - 20;
                        if (ty < area.top) ty = pt.y + 10;
                        cctx.fillStyle = "rgba(255, 255, 255, 0.85)";
                        cctx.fillRect(tx, ty, w + 10, 15);
                        cctx.fillStyle = C.slate900;
                        cctx.fillText(val, tx + 5, ty + 11);
                        cctx.restore();
                    };
                    if (maxIdx >= 0) drawTag(maxIdx, C.teal600);
                    if (minIdx >= 0 && minIdx !== maxIdx) drawTag(minIdx, C.red600);
                },
            }],
        }));
    }

    gkChannelColor(name) {
        const MAP = {
            "Dine-in / Walk-in": CHART_COLORS[0],
            "Gofood": CHART_COLORS[1],
            "Grabfood": CHART_COLORS[2],
            "Shopeefood": CHART_COLORS[3],
            "ShopeeFood": CHART_COLORS[3],
        };
        return MAP[name] || null;
    }

    renderDonutChannels(Chart, channels) {
        const el = document.querySelector(".gk-chart-channel canvas");
        if (!el) return;
        const total = channels.reduce((s, c) => s + c.amount, 0);
        this.state.charts.push(new Chart(el, {
            type: "doughnut",
            data: {
                labels: channels.map(c => c.name),
                datasets: [{
                    data: channels.map(c => c.amount),
                    backgroundColor: channels.map((c) => this.gkChannelColor(c.name) || C.slate500),
                    borderWidth: 2,
                    borderColor: "#fff",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: { legend: { display: false } },
            },
            plugins: [{
                id: "centerText",
                afterDraw(chart) {
                    const { ctx } = chart;
                    const meta = chart.getDatasetMeta(0);
                    if (!meta.data.length) return;
                    const { x, y } = meta.data[0];
                    ctx.save();
                    ctx.textAlign = "center";
                    ctx.font = "700 18px 'Inter', 'Segoe UI', sans-serif";
                    ctx.fillStyle = C.slate900;
                    ctx.fillText(formatRp(total, true), x, y - 4);
                    ctx.font = "12px 'Inter', 'Segoe UI', sans-serif";
                    ctx.fillStyle = C.slate500;
                    ctx.fillText("Total Omzet", x, y + 14);
                    ctx.restore();
                },
            }],
        }));
    }

    scrollTop() {
        if (this.mainRef && this.mainRef.el) this.mainRef.el.scrollTop = 0;
    }

    selectTab(tabId) {
        this.state.activeTab = tabId;
        this.closeSidebar();
        this.scrollTop();
        setTimeout(() => this.renderCharts(), 50);
    }

    toggleOutletMenu() {
        this.state.outletMenuOpen = !this.state.outletMenuOpen;
    }

    selectOutlet(opt) {
        this.state.outletFilter = { id: opt.id, name: opt.name, ids: opt.ids };
        this.state.outletMenuOpen = false;
        this.scrollTop();
        this.load();
    }

    pctArrow(vsValue) {
        if (vsValue === null || vsValue === undefined) return null;
        const n = Math.abs(Number(vsValue)).toFixed(1).replace(".", ",");
        return `${vsValue >= 0 ? "▲" : "▼"} ${n}%`;
    }

    barPct(amount, max) {
        return max ? `${Math.max(2, Math.round(amount / max * 100))}%` : "0%";
    }

    gkExpenseColor(category) {
        const MAP = {
            "hpp": C.teal600,
            "depreciation": C.navy400,
            "operational": C.amber500,
        };
        return MAP[category] || C.slate500;
    }

    gkPaymentColor(group) {
        const MAP = {
            "qris": C.teal600,
            "cash": C.amber500,
            "ewallet": C.navy400,
            "card": C.navy500,
        };
        return MAP[group] || C.slate500;
    }

    pctLabel(amount, total) {
        if (!total) return "";
        return ` · ${(amount / total * 100).toFixed(1).replace(".", ",")}%`;
    }

    paymentsTotal() {
        const p = (this.state.data && this.state.data.sales && this.state.data.sales.payments) || [];
        return p.reduce((s, x) => s + (x.amount || 0), 0);
    }

    cashTotal() {
        const c = (this.state.data && this.state.data.finance && this.state.data.finance.cash_positions) || [];
        return c.reduce((s, x) => s + (x.balance || 0), 0);
    }

    cashKindLabel(kind) {
        return { kas: "Kas", ewallet: "E-Wallet", bank: "Bank" }[kind] || kind;
    }

    cashCardColor(idx, accent = false) {
        const CASH_PALETTE = [0, 1, 2, 4, 5].map((i) => CHART_COLORS[i]);
        const hex = CASH_PALETTE[idx % CASH_PALETTE.length];
        if (accent) return hex;
        const n = parseInt(hex.slice(1), 16);
        const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
        return `rgba(${r}, ${g}, ${b}, 0.10)`;
    }

    // --- Beranda helpers (F1) ---
    // OVERHAUL 15 Sep (K1): helper hero band, gauge, dan heroDelta dihapus —
    // Laba Bersih tampil sebagai KPI ke-5.
    berandaKpi(key) {
        const b = this.state.data && this.state.data.beranda;
        if (b && b.kpi && b.kpi[key] !== undefined) return b.kpi[key];
        const f = (this.state.data && this.state.data.finance) || {};
        const MAP = {
            net_revenue: f.income_total || 0,
            hpp_total: f.hpp_total || 0,
            gross_profit: (f.income_total || 0) - (f.hpp_total || 0),
            opex: (f.expense_total || 0) - (f.hpp_total || 0),
            net_profit: f.net_profit || 0,
            margin_pct: f.income_total ? (f.net_profit || 0)/(f.income_total)*100 : 0,
        };
        return MAP[key] ?? 0;
    }
    berandaVs(key) {
        const b = this.state.data && this.state.data.beranda;
        if (b && b.vs && b.vs[key] !== undefined) return b.vs[key];
        return null;
    }
    berandaKas(key) {
        const ks = this.state.data && this.state.data.beranda && this.state.data.beranda.kas_settlement;
        if (ks && ks[key] !== undefined) return ks[key];
        return 0;
    }
    berandaArus(key) {
        const a = this.state.data && this.state.data.beranda && this.state.data.beranda.arus_kas_psak;
        if (a && a[key] !== undefined) return a[key];
        return 0;
    }
    berandaNeraca(key) {
        const s = this.state.data && this.state.data.beranda && this.state.data.beranda.snapshot_neraca;
        if (s && s[key] !== undefined) return s[key];
        const fb = (this.state.data && this.state.data.finance && this.state.data.finance.balance) || {};
        const MAP = { aset: fb.total_assets||0, kewajiban: fb.liabilities||0, ekuitas: fb.equity||0, laba_ditahan: fb.net_income_ytd||0, total_liab_ekuitas: fb.total_liab_equity||0 };
        return MAP[key] ?? 0;
    }
    // ==================================================================
    // BERANDA — KARTU KPI (mock: KpiCard)
    // ==================================================================
    /** 5 KPI utama: nilai, sub-rasio, delta vs periode lalu, ikon, tooltip. */
    kpiCards() {
        const income = this.berandaKpi("net_revenue") || 0;
        const hpp = this.berandaKpi("hpp_total") || 0;
        const gross = this.berandaKpi("gross_profit") || 0;
        const opex = this.berandaKpi("opex") || 0;
        const net = this.berandaKpi("net_profit") || 0;
        const share = (v) =>
            income ? `${((v / income) * 100).toFixed(1).replace(".", ",")}% dari revenue` : "—";
        const vs = (key) => {
            const v = this.berandaVs(key);
            if (v === null || v === undefined) return { text: "— tanpa pembanding", pos: null };
            return { text: `${this.pctArrow(v)} vs periode lalu`, pos: v >= 0 };
        };
        const dRev = vs("net_revenue");
        const dHpp = vs("hpp_total");
        const dGross = vs("gross_profit");
        const dOpex = vs("opex");
        const dNet = vs("net_profit");
        return [
            {
                label: "Net Revenue",
                value: formatRp(income, true),
                raw: income,
                sub: this.rangeLabel,
                delta: dRev.text,
                pos: dRev.pos,
                badge: "GL",
                tone: "",
                icon: ICONS.revenue,
                tip: "Total pendapatan bersih setelah diskon dan retur, sebelum PPN. Mencakup seluruh channel penjualan dari outlet yang dipilih.",
            },
            {
                label: "HPP",
                value: formatRp(hpp, true),
                raw: hpp,
                sub: share(hpp),
                delta: dHpp.text,
                pos: dHpp.pos,
                badge: "MIS",
                tone: "",
                icon: ICONS.hpp,
                tip: "Harga Pokok Penjualan: bahan baku dan biaya langsung. Angka headline diambil dari compute MIS Builder (kanonik), valuasi stok memakai FIFO real-time.",
            },
            {
                label: "Gross Profit",
                value: formatRp(gross, true),
                raw: gross,
                sub: income ? `Margin ${((gross / income) * 100).toFixed(1).replace(".", ",")}%` : "—",
                delta: dGross.text,
                pos: dGross.pos,
                badge: "MIS",
                tone: "teal",
                icon: ICONS.gross,
                tip: "Gross Profit = Net Revenue − HPP. Margin menunjukkan efisiensi setelah biaya bahan, sebelum beban operasional.",
            },
            {
                label: "OPEX",
                value: formatRp(opex, true),
                raw: opex,
                sub: share(opex),
                delta: dOpex.text,
                pos: dOpex.pos,
                badge: "GL",
                tone: "amber",
                icon: ICONS.opex,
                tip: "Beban operasional di luar HPP: gaji, sewa, utilitas, pemasaran, dan penyusutan.",
            },
            {
                label: "Laba sblm Pajak",
                value: formatRp(net, true),
                raw: net,
                sub: income ? `±estimasi · margin ${((net / income) * 100).toFixed(1).replace(".", ",")}%` : "±estimasi",
                delta: dNet.text,
                pos: dNet.pos,
                badge: "estimasi",
                tone: "emerald",
                icon: ICONS.profit,
                tip: "Estimasi laba sebelum PPh Badan. Angka final bergantung pada akrual pajak yang masih dalam review — tanda ± menandai angka draft.",
            },
        ];
    }

    // ==================================================================
    // KPI STRIP PER TAB (mock: KpiCard) — dipakai template TabKpis
    // ==================================================================
    /**
     * Kartu KPI untuk tab yang sedang aktif. Beranda memakai kartu mock
     * (kpiCards); enam tab lain disusun dari payload live yang sudah ada.
     *
     * Kontrak tiap kartu:
     *   { label, value, raw, sub, delta, pos, tone, badge, icon, tip }
     * pos = true (naik/baik) · false (turun/buruk) · null (tanpa pembanding)
     * → menentukan warna aksen bawah kartu (is-up/is-down/is-neutral).
     */
    tabKpis() {
        const BUILDERS = {
            beranda: () => this.kpiCards(),
            laporan: () => this.kpiLaporan(),
            penjualan: () => this.kpiPenjualan(),
            hpp: () => this.kpiBiaya(),
            kas: () => this.kpiKas(),
            aset: () => this.kpiAset(),
            persediaan: () => this.kpiPersediaan(),
            pajak: () => this.kpiPajak(),
        };
        const build = BUILDERS[this.state.activeTab];
        return build ? build() : [];
    }

    _fin() { return (this.state.data && this.state.data.finance) || {}; }
    _sum() { return (this.state.data && this.state.data.summary) || {}; }
    _ops() { return (this.state.data && this.state.data.ops) || {}; }

    /** Persentase bagian dari total, atau "—" bila total nol. */
    _pct(value, total) {
        return total ? formatPct((value / total) * 100) : "—";
    }

    /** Porsi nilai terhadap total, gaya mock ("32,4% dari pendapatan"). */
    _share(value, total, suffix = "dari revenue") {
        return `${this._pct(value, total)} ${suffix}`;
    }

    /** Angka cacah gaya Indonesia (pemisah ribuan titik). */
    _count(v) {
        return Number(v || 0).toLocaleString("id-ID");
    }

    /**
     * Delta vs periode pembanding. `goodWhenDown` dipakai kartu biaya: nilai
     * naik tetap ditampilkan ▲ tapi diwarnai merah karena justru memburuk.
     */
    _vsDelta(vsValue, opts = {}) {
        if (vsValue === null || vsValue === undefined) {
            return { text: "— tanpa pembanding", pos: null };
        }
        const up = Number(vsValue) >= 0;
        const good = opts.goodWhenDown ? !up : up;
        return { text: `${this.pctArrow(vsValue)} vs ${opts.base || "periode lalu"}`, pos: good };
    }

    /** Label manusiawi kategori beban payload (hpp/depreciation/operational). */
    expenseCategoryLabel(category) {
        return {
            hpp: "HPP",
            depreciation: "Penyusutan",
            operational: "Operasional",
        }[category] || "Lainnya";
    }

    /** Tab Laporan — ringkasan laba rugi periode berjalan. */
    kpiLaporan() {
        const fin = this._fin();
        const sum = this._sum();
        const income = fin.income_total || 0;
        const expense = fin.expense_total || 0;
        const net = fin.net_profit || 0;
        const margin = income ? (net / income) * 100 : 0;
        const dRev = this._vsDelta(sum.vs && sum.vs.amount_total);
        const dBiaya = this._vsDelta(this.berandaVs("opex"), { goodWhenDown: true });
        const dNet = this._vsDelta(fin.net_profit_prev);
        return [
            {
                label: "Net Revenue",
                value: formatRp(income, true),
                raw: income,
                sub: `${this._count(sum.order_count)} transaksi POS`,
                delta: dRev.text,
                pos: dRev.pos,
                tone: "",
                badge: "GL",
                icon: ICONS.revenue,
                tip: "Pendapatan bersih seluruh channel pada periode terpilih, diambil dari buku besar (compute MIS Builder). Mencakup penjualan POS maupun korporat.",
            },
            {
                label: "Total Biaya",
                value: formatRp(expense, true),
                raw: expense,
                sub: this._share(expense, income),
                delta: dBiaya.text,
                pos: dBiaya.pos,
                tone: "amber",
                badge: "GL",
                icon: ICONS.opex,
                tip: "Seluruh beban periode: HPP, beban operasional, dan penyusutan. Porsi dihitung terhadap pendapatan bersih.",
            },
            {
                label: "Laba Bersih",
                value: formatRp(net, true),
                raw: net,
                sub: `${formatPct(margin)} margin bersih`,
                delta: dNet.text,
                pos: dNet.pos,
                tone: "emerald",
                badge: "MIS",
                icon: ICONS.profit,
                tip: "Laba bersih sebelum pajak dari compute MIS Builder. Pembanding memakai laba periode sebelumnya dengan panjang rentang yang sama.",
            },
            {
                label: "Margin Bersih",
                value: formatPct(margin),
                raw: margin,
                sub: "pendapatan − seluruh biaya",
                delta: "— target internal 12,0%",
                pos: null,
                tone: "teal",
                badge: "rasio",
                icon: ICONS.gross,
                tip: "Margin bersih = laba bersih ÷ pendapatan bersih. Target 12,0% hanya indikator manajemen, bukan angka akuntansi.",
            },
        ];
    }

    /** Tab Penjualan — volume & nilai transaksi POS. */
    kpiPenjualan() {
        const sum = this._sum();
        const amount = sum.amount_total || 0;
        const orders = sum.order_count || 0;
        const ticket = sum.avg_ticket || 0;
        const vs = sum.vs || {};
        const ch = this.channels();
        const top = ch.length ? ch.reduce((a, b) => (b.amount > a.amount ? b : a)) : null;
        const dAmount = this._vsDelta(vs.amount_total);
        const dOrders = this._vsDelta(vs.order_count);
        const dTicket = this._vsDelta(vs.avg_ticket);
        return [
            {
                label: "Omzet POS",
                value: formatRp(amount, true),
                raw: amount,
                sub: `${this._count(orders)} transaksi`,
                delta: dAmount.text,
                pos: dAmount.pos,
                tone: "",
                badge: "POS",
                icon: ICONS.cart,
                tip: "Total omzet order POS terkonfirmasi pada periode ini, sebelum diskon channel dan komisi platform.",
            },
            {
                label: "Jumlah Transaksi",
                value: this._count(orders),
                raw: orders,
                sub: `${formatRp(sum.avg_daily, true)}/hari rata-rata`,
                delta: dOrders.text,
                pos: dOrders.pos,
                tone: "blue",
                badge: "POS",
                icon: ICONS.wallet,
                tip: "Banyaknya struk POS pada periode ini dari order yang sudah dibayar. Rata-rata harian dibagi jumlah hari kalender periode.",
            },
            {
                label: "Avg Ticket",
                value: formatRp(ticket, true),
                raw: ticket,
                sub: "per transaksi",
                delta: dTicket.text,
                pos: dTicket.pos,
                tone: "teal",
                badge: "POS",
                icon: ICONS.revenue,
                tip: "Rata-rata nilai per transaksi = omzet POS ÷ jumlah transaksi. Berguna memantau naiknya keranjang tanpa menambah jumlah pengunjung.",
            },
            {
                label: top ? `Channel ${top.name}` : "Channel Utama",
                value: top ? formatRp(top.amount, true) : "—",
                raw: top ? top.amount : 0,
                sub: top ? `${formatPct(top.pct)} dari omzet` : "belum ada penjualan",
                delta: `${this._count(ch.length)} channel aktif`,
                pos: null,
                tone: "emerald",
                badge: "channel",
                icon: ICONS.building,
                tip: "Channel penyumbang omzet terbesar pada periode ini. Rincian lengkap per channel ada di kartu Komposisi Channel di bawah.",
            },
        ];
    }

    /** Tab Biaya & HPP — komposisi biaya produksi & operasional. */
    kpiBiaya() {
        const fin = this._fin();
        const income = fin.income_total || 0;
        const hpp = fin.hpp_total || 0;
        const expense = fin.expense_total || 0;
        const opex = expense - hpp;
        const dep = fin.depreciation_total || 0;
        const commission = fin.platform_commission || 0;
        const gross = income - hpp;
        const hppVs = fin.hpp_prev
            ? Math.round(((hpp - fin.hpp_prev) / Math.abs(fin.hpp_prev)) * 1000) / 10
            : null;
        const dHpp = this._vsDelta(hppVs, { goodWhenDown: true });
        const dOpex = this._vsDelta(this.berandaVs("opex"), { goodWhenDown: true });
        const dGross = this._vsDelta(this.berandaVs("gross_profit"));
        return [
            {
                label: "HPP",
                value: formatRp(hpp, true),
                raw: hpp,
                sub: this._share(hpp, income),
                delta: dHpp.text,
                pos: dHpp.pos,
                tone: "amber",
                badge: "MIS",
                icon: ICONS.hpp,
                tip: "Harga Pokok Penjualan dari compute MIS Builder (kanonik). Nilai persediaan memakai valuasi FIFO real-time.",
            },
            {
                label: "Beban Operasional",
                value: formatRp(opex, true),
                raw: opex,
                sub: this._share(opex, income),
                delta: dOpex.text,
                pos: dOpex.pos,
                tone: "",
                badge: "GL",
                icon: ICONS.opex,
                tip: "Total beban akun di luar HPP: gaji, sewa, utilitas, pemasaran, dan lain-lain. Porsi dihitung terhadap pendapatan bersih.",
            },
            {
                label: "Penyusutan",
                value: formatRp(dep, true),
                raw: dep,
                sub: "PSAK 16 · register aset",
                delta: "— beban non-kas",
                pos: null,
                tone: "blue",
                badge: "non-kas",
                icon: ICONS.building,
                tip: "Beban penyusutan periode berjalan dari register aset tetap. Beban non-kas, sehingga tetap muncul di arus kas sebagai penyesuaian.",
            },
            {
                label: "Komisi Platform",
                value: formatRp(commission, true),
                raw: commission,
                sub: "potongan delivery",
                delta: "— akun komisi GL",
                pos: null,
                tone: "teal",
                badge: "GL",
                icon: ICONS.wallet,
                tip: "Total komisi platform delivery (GoFood/GrabFood/ShopeeFood) yang tercatat di akun komisi GL.",
            },
            {
                label: "Gross Profit",
                value: formatRp(gross, true),
                raw: gross,
                sub: this._share(gross, income, "margin kotor"),
                delta: dGross.text,
                pos: dGross.pos,
                tone: "emerald",
                badge: "MIS",
                icon: ICONS.gross,
                tip: "Gross Profit = Net Revenue − HPP. Menunjukkan margin setelah biaya bahan, sebelum beban operasional.",
            },
        ];
    }

    /** Tab Kas & Bank — posisi saldo dan mutasi periode. */
    kpiKas() {
        const fin = this._fin();
        const cf = fin.cashflow || {};
        const positions = fin.cash_positions || [];
        const total = positions.reduce((s, p) => s + (p.balance || 0), 0);
        const pending = (this.berandaKas("settlement_pending") || 0) + (this.berandaKas("receivables") || 0);
        const net = cf.net || 0;
        return [
            {
                label: "Saldo Kas & Bank",
                value: formatRp(total, true),
                raw: total,
                sub: `${positions.length} pos keuangan`,
                delta: "saldo kumulatif (posted)",
                pos: null,
                tone: "",
                badge: "GL",
                icon: ICONS.bank,
                tip: "Jumlah saldo seluruh akun kas, bank, dan e-wallet per akhir periode. Angka kumulatif — bukan mutasi periode.",
            },
            {
                label: "Kas Neto Periode",
                value: formatSigned(net),
                raw: net,
                sub: "mutasi kas & bank",
                delta: `${formatRp(cf.in || 0, true)} masuk · ${formatRp(cf.out || 0, true)} keluar`,
                pos: net >= 0,
                tone: net >= 0 ? "emerald" : "red",
                badge: "GL",
                icon: ICONS.cash,
                tip: "Selisih debit dan kredit akun kas/bank pada periode ini. Nilai negatif berarti kas keluar lebih besar daripada yang masuk.",
            },
            {
                label: "Penerimaan",
                value: formatRp(cf.in || 0, true),
                raw: cf.in || 0,
                sub: "debit akun kas/bank",
                delta: "bruto periode",
                pos: null,
                tone: "teal",
                badge: "GL",
                icon: ICONS.wallet,
                tip: "Total debit akun kas/bank pada periode ini: penjualan tunai, pelunasan piutang, dan setoran lain.",
            },
            {
                label: "Settlement & Piutang",
                value: formatRp(pending, true),
                raw: pending,
                sub: "belum terklasifikasi",
                delta: "perlu klarifikasi",
                pos: null,
                tone: "amber",
                badge: "review",
                icon: ICONS.clock,
                tip: "Settlement POS dan piutang korporat yang belum diklasifikasi sebagai kas. Konfirmasi klasifikasi sebelum dipakai di laporan final.",
            },
        ];
    }

    /** Tab Aset — register aset tetap & penyusutan. */
    kpiAset() {
        const a = this._ops().assets || {};
        const rows = a.rows || [];
        const gross = a.total_gross || 0;
        const accum = a.total_accum || 0;
        const net = gross - accum;
        const depMonth = rows.reduce((s, r) => s + (r.dep_month || 0), 0);
        return [
            {
                label: "Nilai Perolehan",
                value: formatRp(gross, true),
                raw: gross,
                sub: `${rows.length} aset terdaftar`,
                delta: "perolehan s.d. periode",
                pos: null,
                tone: "",
                badge: "register",
                icon: ICONS.building,
                tip: "Harga perolehan seluruh aset tetap yang terdaftar di register aset OCA, sebelum akumulasi penyusutan.",
            },
            {
                label: "Akumulasi Penyusutan",
                value: formatRp(accum, true),
                raw: accum,
                sub: this._share(accum, gross, "dari perolehan"),
                delta: "— kontra-aset",
                pos: null,
                tone: "amber",
                badge: "s.d. kini",
                icon: ICONS.clock,
                tip: "Total penyusutan yang sudah dibukukan sejak aset diperoleh hingga akhir periode laporan.",
            },
            {
                label: "Nilai Buku Neto",
                value: formatRp(net, true),
                raw: net,
                sub: "perolehan − akumulasi",
                delta: `${rows.length} aset aktif`,
                pos: null,
                tone: "teal",
                badge: "neto",
                icon: ICONS.building,
                tip: "Nilai buku bersih aset tetap: harga perolehan dikurangi akumulasi penyusutan. Angka inilah yang dipakai di neraca.",
            },
            {
                label: "Penyusutan/Bulan",
                value: formatRp(depMonth, true),
                raw: depMonth,
                sub: "beban berjalan seluruh aset",
                delta: "PSAK 16 · garis lurus",
                pos: null,
                tone: "blue",
                badge: "non-kas",
                icon: ICONS.calendar,
                tip: "Total beban penyusutan bulanan seluruh aset aktif. Jadwal 12 bulan ke depan dirinci di tabel Jadwal Penyusutan Mendatang.",
            },
        ];
    }

    /** Tab Persediaan — nilai stok per gudang & susut. */
    /** Tab Pajak — ringkasan PBJT (Pajak Daerah F&B) periode berjalan. */
    kpiPajak() {
        const p = (this.state.data && this.state.data.pbjt) || {};
        const t = p.totals || {};
        const rows = p.per_outlet || [];
        const realTax = t.real_tax || 0;
        const negotiated = t.negotiated || 0;
        const gap = t.gap || 0;
        const rate = rows.length ? rows[0].rate : 10;
        const incl = rows.length ? rows[0].price_include : true;
        const top = rows.length
            ? rows.reduce((a, b) => ((b.real_tax || 0) > (a.real_tax || 0) ? b : a))
            : null;
        return [
            {
                label: "PBJT Riil",
                value: formatRp(realTax, true),
                raw: realTax,
                sub: `${formatPct(rate)} ${incl ? "termasuk harga" : "di atas harga"}`,
                delta: `${rows.length} outlet terdaftar`,
                pos: null,
                tone: "amber",
                badge: "PBJT",
                icon: ICONS.revenue,
                tip: "PBJT terutang menurut penjualan POS periode ini. Dasar: Perda Kota Makassar No. 1 Tahun 2024 (tarif 10%).",
            },
            {
                label: "DPP PBJT",
                value: formatRp(t.dpp || 0, true),
                raw: t.dpp || 0,
                sub: "dasar pengenaan pajak",
                delta: "penjualan bruto − PBJT",
                pos: null,
                tone: "blue",
                badge: "DPP",
                icon: ICONS.gross,
                tip: "Dasar Pengenaan Pajak: penjualan bruto dikurangi unsur PBJT (harga sudah termasuk pajak).",
            },
            {
                label: "Dibayar ke Bapenda",
                value: formatRp(negotiated, true),
                raw: negotiated,
                sub: negotiated ? "hasil negoisasi/penyetoran" : "belum diisi",
                delta: "input manual rekonsiliasi",
                pos: null,
                tone: "teal",
                badge: "setor",
                icon: ICONS.bank,
                tip: "Nilai PBJT yang benar-benar disetorkan/dinegosiasikan ke Bapenda, diisi pada menu Rekonsiliasi PBJT.",
            },
            {
                label: "Selisih (Gap)",
                value: formatRp(gap, true),
                raw: gap,
                sub: top ? `outlet terbesar: ${top.outlet}` : "belum ada data",
                delta: gap > 0 ? "riil > dibayar" : "riil ≤ dibayar",
                pos: gap <= 0,
                tone: gap > 0 ? "amber" : "emerald",
                badge: "gap",
                icon: ICONS.profit,
                tip: "Selisih antara PBJT riil dan nilai yang dibayar ke Bapenda. Positif = potensi kurang setor (perlu review).",
            },
        ];
    }

    kpiPersediaan() {
        const ops = this._ops();
        const inv = ops.inventory || {};
        const waste = ops.waste || {};
        const perWh = inv.per_warehouse || [];
        const total = inv.total || 0;
        const qty = perWh.reduce((s, w) => s + (w.qty || 0), 0);
        const top = perWh.length ? perWh.reduce((a, b) => ((b.value || 0) > (a.value || 0) ? b : a)) : null;
        const wasteQty = (waste.rows || []).reduce((s, r) => s + (r.qty || 0), 0);
        const hasWaste = !!waste.count;
        return [
            {
                label: "Nilai Persediaan",
                value: formatRp(total, true),
                raw: total,
                sub: `${perWh.length} gudang · valuasi FIFO`,
                delta: "real-time (stock valuation)",
                pos: null,
                tone: "",
                badge: "FIFO",
                icon: ICONS.box,
                tip: "Nilai persediaan seluruh gudang pada akhir periode memakai metode FIFO real-time dari modul Stock Valuation.",
            },
            {
                label: top ? `Gudang ${top.warehouse}` : "Gudang Terbesar",
                value: top ? formatRp(top.value, true) : "—",
                raw: top ? top.value : 0,
                sub: top ? `${this._count(top.qty)} unit · ${this._pct(top.value, total)} dari total` : "belum ada stok",
                delta: `${perWh.length} gudang aktif`,
                pos: null,
                tone: "teal",
                badge: "FIFO",
                icon: ICONS.building,
                tip: "Gudang dengan nilai persediaan terbesar pada periode ini. Rincian nilai dan qty per gudang ada di tabel di bawah.",
            },
            {
                label: "Total Qty Stok",
                value: this._count(qty),
                raw: qty,
                sub: "unit di seluruh gudang",
                delta: "kuantitas on-hand",
                pos: null,
                tone: "blue",
                badge: "FIFO",
                icon: ICONS.box,
                tip: "Jumlah unit on-hand di seluruh gudang — pembanding kasar nilai persediaan, bukan ukuran nilai rupiah.",
            },
            {
                label: "Waste / Susut",
                value: this._count(waste.count || 0),
                raw: waste.count || 0,
                sub: wasteQty ? `${this._count(wasteQty)} unit discrap` : "tidak ada scrap",
                delta: hasWaste ? "perlu perhatian" : "terkendali",
                pos: !hasWaste,
                tone: hasWaste ? "amber" : "emerald",
                badge: "scrap",
                icon: ICONS.clock,
                tip: "Banyaknya transaksi scrap (state done) pada periode ini beserta total unit yang dibuang. Nilai susut mengikuti valuasi FIFO.",
            },
        ];
    }

    // ==================================================================
    // BERANDA — TREN BULANAN & OUTLET
    // ==================================================================
    /** Baris laba bulanan (6 bulan terakhir) dari backend. */
    monthlyRows() {
        return (this.state.data && this.state.data.beranda && this.state.data.beranda.laba_bulanan) || [];
    }

    /** Kontribusi omzet per outlet + porsinya. */
    outletBars() {
        const outlets = (this.state.data && this.state.data.summary && this.state.data.summary.outlets) || [];
        const total = outlets.reduce((s, o) => s + (o.amount_total || 0), 0) || 1;
        return outlets.map((o) => ({
            outlet: o.name,
            revenue: o.amount_total || 0,
            order_count: o.order_count || 0,
            pct: ((o.amount_total || 0) / total) * 100,
        }));
    }

    // ==================================================================
    // BERANDA — DONUT KATEGORI & CHANNEL
    // ==================================================================
    /** 5 kategori produk (category_map.json) — sumber donut Beranda. */
    kategori() {
        const rows = (this.state.data && this.state.data.beranda && this.state.data.beranda.kategori_produk) || [];
        return rows.map((c) => ({
            name: c.name,
            amount: c.amount || 0,
            pct: c.pct || 0,
            color: this.gkKategoriColor(c.name),
        }));
    }

    get hasKategori() {
        return this.kategori().length > 0;
    }

    /** Channel penjualan (dipakai tab Penjualan + fallback donut Beranda). */
    channels() {
        const rows = (this.state.data && this.state.data.sales && this.state.data.sales.channels) || [];
        const total = rows.reduce((s, c) => s + (c.amount || 0), 0) || 1;
        return rows.map((c) => ({
            name: c.name,
            amount: c.amount || 0,
            order_count: c.order_count || 0,
            pct: ((c.amount || 0) / total) * 100,
            color: this.gkChannelColor(c.name) || CHART_COLORS[5],
        }));
    }

    /**
     * Rincian delivery: bruto (omzet channel delivery) − komisi platform
     * (akun komisi di GL) = net delivery. Semua live; bernilai 0 bila tidak
     * ada penjualan platform pada periode ini.
     */
    deliveryDetail() {
        const rows = this.channels().filter((c) => /deliver|gofood|grabfood|shopeefood/i.test(c.name));
        const gross = rows.reduce((s, c) => s + c.amount, 0);
        const commission = (this.state.data && this.state.data.finance && this.state.data.finance.platform_commission) || 0;
        return { has: rows.length > 0, gross, commission, net: gross - commission };
    }

    // ==================================================================
    // BERANDA — KAS / BANK / SETTLEMENT
    // ==================================================================
    /**
     * Kartu posisi kas & bank dari GL. Bila tidak ada posisi (mis. periode
     * tanpa mutasi) → jatuh ke kartu demo. Kartu settlement POS selalu
     * ditambahkan bila saldo outstanding-nya ada.
     */
    cashCards() {
        const positions = (this.state.data && this.state.data.finance && this.state.data.finance.cash_positions) || [];
        let cards;
        if (positions.length) {
            cards = positions.map((p) => {
                const name = (p.name || "").toLowerCase();
                const review = p.kind === "ewallet" || /qris|settlement|outstanding|piutang/.test(name);
                return {
                    label: p.name,
                    val: p.balance,
                    status: review ? "review" : "pass",
                    note: review ? "Settlement belum diklasifikasi" : "Saldo buku (posted)",
                    demo: false,
                };
            });
        } else {
            cards = DEMO_CASH_CARDS.map((c) => ({ ...c, demo: true }));
        }
        const settle = this.berandaKas("settlement_pending") || 0;
        const receivable = this.berandaKas("receivables") || 0;
        if (!cards.some((c) => c.demo) && Math.abs(settle) > 0.5) {
            cards.push({
                label: "Settlement POS (1103.06)",
                val: settle,
                status: "review",
                note: "Piutang settlement belum cair",
                demo: false,
            });
        }
        if (!cards.some((c) => c.demo) && Math.abs(receivable) > 0.5) {
            cards.push({
                label: "Piutang Korporat",
                val: receivable,
                status: "review",
                note: "Faktur belum lunas",
                demo: false,
            });
        }
        return cards;
    }

    get cashCardsAreDemo() {
        return this.cashCards().some((c) => c.demo);
    }

    cashSummaryTotal() {
        return this.cashCards().reduce((s, c) => s + (c.val || 0), 0);
    }

    // ==================================================================
    // BERANDA — ARUS KAS (PSAK 2, metode tak langsung)
    // ==================================================================
    /** Baris detail diturunkan dari agregat live; selisihnya jadi baris plug. */
    cfRows() {
        const fin = (this.state.data && this.state.data.finance) || {};
        const operasi = this.berandaArus("operasi") || 0;
        const laba = fin.net_profit || 0;
        const dep = fin.depreciation_total || 0;
        if (this.state.cfTab === "operasi") {
            return [
                { label: "Laba sblm Pajak", val: laba },
                { label: "Penyesuaian Depresiasi", val: dep },
                { label: "Perub. Modal Kerja (piutang/persediaan/utang)", val: operasi - laba - dep },
            ];
        }
        if (this.state.cfTab === "investasi") {
            return [{ label: "Perub. Aset Tetap (neto)", val: this.berandaArus("investasi") || 0 }];
        }
        return [{ label: "Setoran Modal / Pendanaan (plug Δ kas)", val: this.berandaArus("pendanaan") || 0 }];
    }

    cfTotal() {
        return this.cfRows().reduce((s, r) => s + r.val, 0);
    }

    cfTotalLabel() {
        return { operasi: "Kas Neto Operasi", investasi: "Kas Neto Investasi", pendanaan: "Kas Neto Pendanaan" }[this.state.cfTab];
    }

    cfTabLabel() {
        return { operasi: "Aktivitas Operasi", investasi: "Aktivitas Investasi", pendanaan: "Aktivitas Pendanaan" }[this.state.cfTab];
    }

    selectCfTab(key) {
        this.state.cfTab = key;
        setTimeout(() => this.renderCharts(), 50);
    }

    // ==================================================================
    // BERANDA — SNAPSHOT NERACA & BALANCE CHECK
    // ==================================================================
    /** Sisi aset: kas+bank, persediaan, aset tetap bruto/akumulasi/neto. */
    neracaAssets() {
        const kas = (this.berandaKas("kas") || 0) + (this.berandaKas("bank") || 0);
        const inv = this.berandaNeracaInventory();
        const assets = (this.state.data && this.state.data.ops && this.state.data.ops.assets) || {};
        const gross = assets.total_gross || 0;
        const accum = assets.total_accum || 0;
        const netFixed = gross - accum;
        const totalAssets = this.berandaNeraca("aset") || 0;
        const other = totalAssets - (kas + inv + netFixed);
        const rows = [
            { label: "Kas / Bank / Settlement", val: kas, note: "Posisi saldo buku" },
            { label: "Persediaan (FIFO)", val: inv, note: "Valuasi stok per gudang" },
            { label: "Aset Tetap — Bruto", val: gross, note: "Perolehan s.d. periode" },
            { label: "Akumulasi Penyusutan", val: -accum, note: "s.d. periode berjalan" },
            { label: "Aset Tetap — Neto", val: netFixed, note: "Bruto − Akumulasi", bold: true },
        ];
        if (Math.abs(other) > 0.5) {
            rows.push({ label: "Aset Lainnya", val: other, note: "Piutang, uang muka, aset lancar lain" });
        }
        return rows;
    }

    berandaNeracaInventory() {
        const o = (this.state.data && this.state.data.ops && this.state.data.ops.inventory) || {};
        return o.total || 0;
    }

    /** Sisi ekuitas: ekuitas tercatat, laba periode, laba ditahan YTD. */
    neracaEquity() {
        const bal = (this.state.data && this.state.data.finance && this.state.data.finance.balance) || {};
        const period = (this.state.data && this.state.data.finance && this.state.data.finance.net_profit) || 0;
        return [
            { label: "Ekuitas Tercatat", val: bal.equity || 0, note: "Modal disetor + saldo laba" },
            { label: "Laba Periode Berjalan", val: period, note: "± estimasi draft" },
            { label: "Laba Ditahan (YTD)", val: bal.net_income_ytd || 0, note: "Akumulasi tahun berjalan" },
        ];
    }

    neracaEquityTotal() {
        const bal = (this.state.data && this.state.data.finance && this.state.data.finance.balance) || {};
        return (bal.equity || 0) + (bal.net_income_ytd || 0);
    }

    /** Selisih aset vs liabilitas+ekuitas — indikator kelengkapan opening balance. */
    balanceCheck() {
        const aset = this.berandaNeraca("aset") || 0;
        const liabEq = this.berandaNeraca("total_liab_ekuitas") || 0;
        const max = Math.max(Math.abs(aset), Math.abs(liabEq));
        const pct = max ? (Math.min(Math.abs(aset), Math.abs(liabEq)) / max) * 100 : 0;
        const diff = aset - liabEq;
        return { pct, diff, aset, liabEq, ok: Math.abs(diff) < 1 };
    }

    // ==================================================================
    // BERANDA — PANEL PSAK (data demo) & TABEL LABA RUGI
    // ==================================================================
    get psak() {
        return DEMO_PSAK;
    }

    get psakCounts() {
        const p = DEMO_PSAK;
        const total = p.pass.length + p.review.length + p.pending.length;
        return {
            pass: p.pass.length,
            review: p.review.length,
            pending: p.pending.length,
            total,
            readiness: total ? ((p.pass.length + p.review.length) / total) * 100 : 0,
        };
    }

    psakWidth(kind) {
        const c = this.psakCounts;
        const num = kind === "pass" ? c.pass : kind === "review" ? c.review : c.pending;
        return `${(num / c.total) * 100}%`;
    }

    /**
     * Tabel laba rugi bulanan. Backend (beranda.laba_bulanan) kini mengirim
     * rincian HPP / beban operasional / komisi platform / penyusutan per bulan
     * sebagai bucket EKSKLUSIF, sehingga `hpp + operational + commission +
     * depreciation == expense` — jumlah komponennya selalu sama dengan kolom
     * Total Biaya (tabel bisa di-foot tanpa double count).
     */
    plRows() {
        const rows = this.monthlyRows().map((r) => {
            const rev = r.income || 0;
            const net = r.value || 0;
            return {
                bulan: r.label,
                revenue: rev,
                hpp: r.hpp || 0,
                operational: r.operational || 0,
                commission: r.commission || 0,
                depreciation: r.depreciation || 0,
                expense: r.expense || 0,
                net,
                margin: rev ? (net / rev) * 100 : 0,
                isTotal: false,
            };
        });
        if (rows.length) {
            const KEYS = ["revenue", "hpp", "operational", "commission", "depreciation", "expense", "net"];
            const sum = {};
            for (const key of KEYS) {
                sum[key] = rows.reduce((acc, r) => acc + r[key], 0);
            }
            rows.push({
                bulan: "TOTAL",
                ...sum,
                margin: sum.revenue ? (sum.net / sum.revenue) * 100 : 0,
                isTotal: true,
            });
        }
        return rows;
    }

    // ==================================================================
    // MODAL — AUDIT TRAIL (data demo)
    // ==================================================================
    get auditTrail() {
        return DEMO_AUDIT;
    }

    openModal(key) {
        // A11Y (Fase 5): simpan elemen pemicu + pindahkan fokus ke dialog,
        // supaya role="dialog"/aria-modal="true" benar-benar berlaku untuk
        // pengguna keyboard & screen reader.
        this._modalReturnFocus = document.activeElement;
        this.state.modal = key;
        setTimeout(() => {
            const el = this.modalRef.el;
            if (el) el.focus();
        }, 0);
    }

    closeModal() {
        this.state.modal = null;
        const back = this._modalReturnFocus;
        this._modalReturnFocus = null;
        if (back && typeof back.focus === "function") back.focus();
    }

    /** Dipakai sebagai t-on-click.stop pada kartu modal (tahan klik agar
     *  tidak meneruskan event ke overlay penutup). */
    noopModalClick() {}

    // CATATAN / RENCANA (belum dikerjakan): tampilan PDF ingin memakai grafik
    // gaya Power BI (bukan window.print() polos). Pengerjaannya MENUNGGU addon
    // "Altman Z-Score + tren + gross profit" selesai lebih dulu.
    printReport() { window.print(); }

    async exportExcel() {
        // F5: ekspor XLSX Laba Rugi (MIS Builder) via report_actions — satu
        // sumber dengan Report Shell, memakai periode & outlet yang aktif.
        // report_key "profit_loss_mis" (F5a) = laporan utama dashboard.
        if (this.state.exporting) return;
        this.state.exporting = true;
        try {
            const action = await this.orm.call(
                "geprekyukss.dashboard.report.actions",
                "get_report_export_action",
                [
                    "profit_loss_mis",
                    {
                        date_from: this.period.date_from,
                        date_to: this.period.date_to,
                        outlet_ids: this.state.outletFilter.ids,
                    },
                    "xlsx",
                ],
            );
            await this.action.doAction(action);
        } catch (e) {
            console.error("dashboard xlsx export failed", e);
            const msg =
                (e && e.message && e.message.data && e.message.data.message) ||
                (e && e.message) ||
                "Ekspor XLSX gagal.";
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }

    openReports(reportKey = null) {
        const props = {
            initialYear: 2026,
            initialMonth: 8,
            outletFilter: { ...this.state.outletFilter },
        };
        // derive year/month from date_from for deep-link context
        if (this.state.date_from) {
            const [y,m] = this.state.date_from.split("-").map(Number);
            props.initialYear = y; props.initialMonth = m;
        }
        if (reportKey) props.initialReport = reportKey;
        this.action.doAction("geprekyukss_dashboard.action_geprekyukss_reports", { props });
    }
}

registry.category("actions").add("geprekyukss_dashboard.main", GkDashboard);
