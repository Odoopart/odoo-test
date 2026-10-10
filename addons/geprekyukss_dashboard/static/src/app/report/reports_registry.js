/** @odoo-module **/

/**
 * Registry laporan (F1 — roadmap §B.4 / keputusan §G).
 * Sumber kebenaran konfigurasi UI; engine & data tetap di Python
 * (geprekyukss.dashboard.report.actions). Menambah laporan = menambah
 * entry di sini (+ adapter Python), tanpa menyentuh shell.
 *
 * renderer:
 *   "table"  → <ReportTable> (AFR: rows/columns JSON dari adapter Python)
 *   "matrix" → <ReportMatrix> (MIS Builder: payload asli compute())
 *
 * group (F-UI.2 v2 — sidebar terpadu gaya FinanceFlow): pengelompokan
 * semantik yang dipakai KEDUA sidebar (dashboard & report shell) via
 * getGroupedReports() — satu sumber, tidak mungkin beda struktur.
 */

export const REPORTS = {
    trial_balance: {
        label: "Trial Balance",
        group: "mutasi",
        icon: "fa-balance-scale",
        renderer: "table",
        engine: "AFR",
        description: "Saldo seluruh akun pada akhir periode",
    },
    general_ledger: {
        label: "Buku Besar",
        group: "mutasi",
        icon: "fa-book",
        renderer: "table",
        engine: "AFR",
        description: "Mutasi detail semua jurnal per akun",
    },
    journal_ledger: {
        label: "Journal Ledger",
        group: "mutasi",
        icon: "fa-files-o",
        renderer: "table",
        engine: "AFR",
        description: "Daftar entry jurnal per buku",
    },
    aged_partner: {
        label: "Umur Piutang",
        group: "piutang",
        icon: "fa-hourglass-half",
        renderer: "table",
        engine: "AFR",
        description: "Aging piutang per partner",
    },
    open_items: {
        label: "Open Items",
        group: "piutang",
        icon: "fa-external-link",
        renderer: "table",
        engine: "AFR",
        description: "Invoice/bill yang belum terlunaskan",
    },
    vat: {
        label: "Laporan PPN",
        group: "pajak",
        icon: "fa-percent",
        renderer: "table",
        engine: "AFR",
        description: "Ringkasan pajak keluaran/masukan",
    },
    cash_flow_mis: {
        label: "Arus Kas",
        group: "ringkasan",
        icon: "fa-exchange",
        renderer: "matrix",
        engine: "MIS Builder",
        description: "Posisi & proyeksi arus kas (MIS Builder)",
    },
    profit_loss_mis: {
        label: "Laba Rugi",
        group: "ringkasan",
        icon: "fa-line-chart",
        renderer: "matrix",
        engine: "MIS Builder",
        description: "Laporan laba rugi bulan berjalan + YTD (MIS Builder, tanpa JE demo)",
    },
    balance_sheet_mis: {
        label: "Neraca",
        group: "ringkasan",
        icon: "fa-building-o",
        renderer: "matrix",
        engine: "MIS Builder",
        description: "Posisi keuangan per akhir bulan berjalan vs bulan lalu (MIS Builder, tanpa JE demo)",
    },
};

export const REPORT_ORDER = [
    "profit_loss_mis",
    "balance_sheet_mis",
    "cash_flow_mis",
    "trial_balance",
    "general_ledger",
    "journal_ledger",
    "aged_partner",
    "open_items",
    "vat",
];

export function getReport(key) {
    return REPORTS[key] || null;
}

/**
 * A1 (audit): laporan akuntansi (AFR/MIS) bersifat KONSOLIDASI — tidak ada
 * dimensi outlet di account.move.line (kedua outlet berbagi journal yang
 * sama, pos.order tidak ter-link ke account.move). Karena itu filter outlet
 * tidak boleh ditampilkan sebagai aktif untuk laporan ini; shell menandainya
 * "Konsolidasi". Tambahkan key di sini bila kelak sebuah laporan benar-benar
 * mendukung filter outlet.
 */
export const OUTLET_FILTER_REPORTS = new Set();

export function supportsOutlet(key) {
    return OUTLET_FILTER_REPORTS.has(key);
}

/**
 * F-UI.2 v2 — pengelompokan semantik sidebar (gaya FinanceFlow: section
 * header uppercase kecil). Urutan grup & laporan dalam grup mengikuti
 * REPORT_ORDER. Dipakai dashboard.xml DAN report_shell.xml.
 */
export const REPORT_GROUPS = [
    { id: "ringkasan", label: "Ringkasan" },
    { id: "mutasi", label: "Mutasi & Saldo" },
    { id: "piutang", label: "Piutang & Hutang" },
    { id: "pajak", label: "Pajak" },
];

export function getGroupedReports() {
    return REPORT_GROUPS
        .map((g) => ({
            ...g,
            reports: REPORT_ORDER.filter((k) => REPORTS[k] && REPORTS[k].group === g.id),
        }))
        .filter((g) => g.reports.length > 0);
}
