/** @odoo-module **/

import { Component, useState, useRef, useExternalListener, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { REPORTS, getGroupedReports, supportsOutlet } from "./reports_registry.js";
import { ReportTable } from "./report_table.js";
import { ReportMatrix } from "./report_matrix.js";
// Shell (topnav/sidebar) dipakai bersama dengan dashboard — brandmark diimpor
// dari satu sumber agar kedua halaman tidak mungkin beda visual.
import { BRANDMARK } from "../dashboard/dashboard.js";

const MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
];

// F-UI.5: label pendek utk rentang kustom ("15 Agu – 10 Sep 2026")
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const MAX_RANGE_DAYS = 366;   // guard: GL bisa puluhan ribu baris utk rentang panjang
const PAGE_SIZE = 50;         // C1: baris per halaman (paginasi server-side)

import { registry } from "@web/core/registry";

/**
 * GkReportPage — halaman laporan (F1, roadmap §B "report shell").
 *
 * Dipasang sebagai client action terpisah dari dashboard utama; menuju
 * kesini dari sidebar dashboard (dashboard.js memanggil doAction dengan
 * tag "geprekyukss_dashboard.reports").
 *
 * Arsitektur Opsi B (roadmap §B.3): komponen ini = <ReportShell> — pemilik
 * filter bar (Q3: minimal + tombol Filter Lanjutan), toolbar export, dan
 * state machine (idle | loading | empty | error | success). Render spesifik
 * didelegasikan ke <ReportTable> / <ReportMatrix> via komponen child.
 *
 * Keputusan terkait (§G roadmap):
 *  - Filter global (bulan + outlet) DIWARISKAN dari dashboard via props —
 *    perubahan bulan/outlet di dashboard langsung terlihat saat kembali,
 *    tapi halaman laporan punya state sendiri agar bisa digeser lepas.
 *  - "Filter Lanjutan" membuka wizard native OCA (bukan filter di shell).
 */
export class GkReportPage extends Component {
    static template = "geprekyukss_dashboard.ReportPage";
    static components = { ReportTable, ReportMatrix };
    static props = {
        // Diteruskan dari dashboard (bila dibuka via sidebar dashboard);
        // opsional — halaman laporan tetap berdiri sendiri tanpa props.
        initialYear: { type: Number, optional: true },
        initialMonth: { type: Number, optional: true },
        outletFilter: { type: Object, optional: true },
        // F-UI.2c: deep-link dari dashboard — buka laporan tertentu langsung
        // (mis. widget AP → "open_items"). Tidak valid → fallback TB senyap.
        initialReport: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.reports = REPORTS;
        // F-UI.2b: struktur grouping untuk sidebar (satu sumber dgn dashboard)
        this.groupedReports = getGroupedReports();
        this.brandmark = BRANDMARK;

        // Deep-link (F-UI.2c): initialReport valid dipakai sebagai laporan awal;
        // selain itu default PoC #1 (§D.2) = TB.
        const startReport =
            this.props.initialReport && REPORTS[this.props.initialReport]
                ? this.props.initialReport
                : "trial_balance";

        const now = new Date();
        this.state = useState({
            activeReport: startReport,
            phase: "idle",                   // idle | loading | empty | error | success
            errorText: "",
            year: this.props.initialYear || 2026,
            month: this.props.initialMonth || 8,  // Agustus 2026 = bulan data pertama
            outletIds: (this.props.outletFilter && this.props.outletFilter.ids) || [],
            outletName: (this.props.outletFilter && this.props.outletFilter.name) || "Semua Outlet",
            outlets: [],
            data: null,                      // payload get_report_data
            exporting: false,
            // Shell mock: sidebar off-canvas < 1024px (hamburger di topnav)
            sidebarOpen: false,
            // Dropdown filter outlet (ditutup saat klik di luar)
            outletMenuOpen: false,
            // F-UI.5: mode filter — "month" (default, perilaku lama) | "custom"
            rangeMode: "month",
            customFrom: "",                  // "YYYY-MM-DD" dari <input type=date>
            customTo: "",
            rangeError: "",                  // validasi inline (from>to, >1 tahun)
            activePreset: "",                // this_month|last_month|ytd|30d|90d|""
            // C1: state paginasi/pencarian/sorting server-side tabel AFR
            page: 0,
            search: "",
            sortKey: null,
            sortDir: "asc",
        });

        this.months = MONTHS;
        this.formatRp = (v) => v;
        this.reportWrapRef = useRef("reportWrap");
        useExternalListener(window, "click", (ev) => {
            const wrap = this.reportWrapRef.el;
            if (wrap && !wrap.contains(ev.target)) {
                this.state.outletMenuOpen = false;
            }
        });

        onWillStart(async () => {
            await this.loadOutlets();
            await this.load();
        });
        // Catatan F-UI.2c: tidak perlu fetch tambahan untuk deep-link —
        // state.activeReport sudah menunjuk laporan tujuan sejak sebelum
        // render pertama, jadi load() di atas sudah memuat laporan yang tepat.
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    get activeReportConfig() {
        return this.reports[this.state.activeReport];
    }

    /** A1: apakah laporan aktif punya dimensi outlet nyata (konsolidasi = false). */
    get outletSupported() {
        return supportsOutlet(this.state.activeReport);
    }

    /** C1: tabel AFR pakai paginasi/pencarian/sorting server-side. */
    get isServerTable() {
        return this.activeReportConfig && this.activeReportConfig.renderer === "table";
    }

    get monthLabel() {
        // F-UI.5: mode kustom → label jadi teks rentang
        if (this.state.rangeMode === "custom" && this.state.customFrom && this.state.customTo) {
            return `${this.formatShort(this.state.customFrom)} – ${this.formatShort(this.state.customTo)}`;
        }
        return `${this.months[this.state.month - 1]} ${this.state.year}`;
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

    get period() {
        // F-UI.5: mode kustom → kembalikan tanggal apa adanya (bisa kosong/
        // invalid saat user sedang mengetik — guard fetch ada di handler &
        // export akan error eksplisit, BUKAN diam-diam pakai periode bulan).
        if (this.state.rangeMode === "custom") {
            return { date_from: this.state.customFrom || "", date_to: this.state.customTo || "" };
        }
        return this._monthPeriod(this.state.year, this.state.month);
    }

    /**
     * F-UI.5 — hint semantik kolom MIS saat rentang kustom (planning §F-UI.5):
     * perilaku engine, ditampilkan apa adanya agar kolom tidak menyesatkan.
     */
    get misRangeHint() {
        if (this.state.rangeMode !== "custom") return "";
        const cfg = this.activeReportConfig;
        if (!cfg || cfg.renderer !== "matrix") return "";
        const f = this.state.customFrom, t = this.state.customTo;
        if (!f || !t || this.state.rangeError) return "";
        if (this.state.activeReport === "balance_sheet_mis") {
            return `Neraca: posisi per akhir ${this.formatShort(t)} vs akhir bulan sebelumnya (window tahun fiskal).`;
        }
        const jan1 = `${t.slice(0, 4)}-01-01`;
        if (f > jan1) {
            return `Kolom YTD tetap 1 Jan ${t.slice(0, 4)} – ${this.formatShort(t)} (bukan sejak awal rentang kustom).`;
        }
        return "";
    }

    async loadOutlets() {
        try {
            const rows = await this.orm.call(
                "geprekyukss.dashboard.data",
                "list_available_outlets",
                [],
            );
            this.state.outlets = rows;
        } catch (e) {
            console.warn("list_available_outlets failed", e);
            this.state.outlets = [];
        }
    }

    async load() {
        const cfg = this.activeReportConfig;
        if (!cfg || cfg.disabled) return;
        // F-UI.5: rentang kustom belum lengkap/invalid → jangan fetch
        // (backend akan raise "date_from & date_to wajib diisi"); biarkan
        // data tampilan sebelumnya tetap tampil sampai input valid.
        if (this.state.rangeMode === "custom" &&
            (!this.state.customFrom || !this.state.customTo || this.state.rangeError)) {
            return;
        }
        this.state.phase = "loading";
        this.state.data = null;
        try {
            const params = {
                date_from: this.period.date_from,
                date_to: this.period.date_to,
                // A1: laporan konsolidasi tidak menerima filter outlet.
                outlet_ids: this.outletSupported ? this.state.outletIds : [],
            };
            // C1: tabel AFR dipaginasi/dicari/diurut di server.
            if (this.isServerTable) {
                params.limit = PAGE_SIZE;
                params.offset = this.state.page * PAGE_SIZE;
                params.search = this.state.search;
                params.sort_key = this.state.sortKey || "";
                params.sort_dir = this.state.sortDir;
            }
            const data = await this.orm.call(
                "geprekyukss.dashboard.report.actions",
                "get_report_data",
                [this.state.activeReport, params],
            );
            if (!data) {
                this.state.phase = "empty";
                return;
            }
            const emptyTable =
                data.kind === "table" && (!data.rows || !data.rows.length);
            const emptyMatrix =
                data.kind === "matrix" && (!data.body || !data.body.length);
            if (emptyTable || emptyMatrix) {
                this.state.data = data;
                this.state.phase = "empty";
                return;
            }
            this.state.data = data;
            this.state.phase = "success";
        } catch (e) {
            console.error("report load failed", e);
            this.state.errorText =
                (e && e.message && e.message.data && e.message.data.message) ||
                (e && e.message) ||
                "Terjadi kesalahan saat memuat laporan.";
            this.state.phase = "error";
        }
    }

    // ------------------------------------------------------------------
    // Shell (topnav + sidebar) — sama dengan dashboard
    // ------------------------------------------------------------------
    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
    }

    // ------------------------------------------------------------------
    // Handlers
    // ------------------------------------------------------------------
    selectReport(key) {
        if (this.state.activeReport === key) return;
        const cfg = this.reports[key];
        if (!cfg || cfg.disabled) return;
        this.state.activeReport = key;
        this._resetPaging();
        this.load();
    }

    /** C1: kembali ke halaman 1 & buang pencarian/sort saat konteks berubah. */
    _resetPaging() {
        this.state.page = 0;
        this.state.search = "";
        this.state.sortKey = null;
        this.state.sortDir = "asc";
    }

    /** C1: handler paginasi dari <ReportTable> (mode server-side). */
    onTablePage(page) {
        this.state.page = Math.max(0, page);
        this.load();
    }

    /** C1: handler pencarian/sorting dari <ReportTable> (mode server-side). */
    onTableQuery({ search, sortKey, sortDir }) {
        if (search !== undefined) this.state.search = search;
        if (sortKey !== undefined) this.state.sortKey = sortKey;
        if (sortDir !== undefined) this.state.sortDir = sortDir;
        this.state.page = 0;
        this.load();
    }

    prevMonth() {
        // F-UI.5: di mode kustom, panah = kembali ke mode bulan
        if (this.state.rangeMode === "custom") { this.setRangeMode("month"); return; }
        let m = this.state.month - 1, y = this.state.year;
        if (m < 1) { m = 12; y -= 1; }
        this.state.month = m; this.state.year = y;
        this._resetPaging();
        this.load();
    }

    nextMonth() {
        if (this.state.rangeMode === "custom") { this.setRangeMode("month"); return; }
        let m = this.state.month + 1, y = this.state.year;
        if (m > 12) { m = 1; y += 1; }
        this.state.month = m; this.state.year = y;
        this._resetPaging();
        this.load();
    }

    // --------------------------------------------------------------
    // F-UI.5 — Date range picker (custom + preset)
    // --------------------------------------------------------------
    setRangeMode(mode) {
        if (this.state.rangeMode === mode) return;
        this.state.rangeError = "";
        if (mode === "custom") {
            // Prefill dari bulan aktif → user tinggal geser, bukan kosong melompong
            const mp = this._monthPeriod(this.state.year, this.state.month);
            this.state.customFrom = mp.date_from;
            this.state.customTo = mp.date_to;
            this.state.activePreset = "";
            this.state.rangeMode = "custom";
        } else {
            this.state.rangeMode = "month";
            this.state.activePreset = "";
        }
        this._resetPaging();
        this.load();
    }

    applyPreset(key) {
        const today = new Date();
        const iso = (d) =>
            `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        let f, t;
        if (key === "this_month") {
            f = new Date(today.getFullYear(), today.getMonth(), 1);
            t = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        } else if (key === "last_month") {
            f = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            t = new Date(today.getFullYear(), today.getMonth(), 0);
        } else if (key === "ytd") {
            f = new Date(today.getFullYear(), 0, 1);
            t = today;
        } else {  // "30d" | "90d"
            t = today;
            f = new Date(today);
            f.setDate(f.getDate() - (key === "30d" ? 29 : 89));
        }
        this.state.customFrom = iso(f);
        this.state.customTo = iso(t);
        this.state.activePreset = key;
        this.state.rangeError = "";
        this._resetPaging();
        this.load();
    }

    onCustomRangeChange() {
        const f = this.state.customFrom, t = this.state.customTo;
        this.state.activePreset = "";
        if (!f || !t) {
            this.state.rangeError = "";   // belum lengkap — jangan fetch, jangan error
            return;
        }
        if (f > t) {
            this.state.rangeError = "Tanggal awal melebihi tanggal akhir.";
            return;
        }
        const days = (new Date(t) - new Date(f)) / 86400000;
        if (days > MAX_RANGE_DAYS) {
            this.state.rangeError = "Rentang maksimal 1 tahun — GL bisa sangat panjang. Gunakan Filter Lanjutan untuk kasus khusus.";
            return;
        }
        this.state.rangeError = "";
        this._resetPaging();
        this.load();
    }

    toggleOutletMenu() {
        this.state.outletMenuOpen = !this.state.outletMenuOpen;
    }

    selectOutlet(opt) {
        // opt: {id: "all"|config_id, name} — shape list_available_outlets
        this.state.outletIds = opt.id === "all" ? [] : [opt.id];
        this.state.outletName = opt.name;
        this.state.outletMenuOpen = false;
        this._resetPaging();
        this.load();
    }

    async exportReport(fmt) {
        if (this.state.exporting) return;
        this.state.exporting = true;
        try {
            const action = await this.orm.call(
                "geprekyukss.dashboard.report.actions",
                "get_report_export_action",
                [this.state.activeReport, {
                    date_from: this.period.date_from,
                    date_to: this.period.date_to,
                    // A1: laporan konsolidasi tidak menerima filter outlet.
                    outlet_ids: this.outletSupported ? this.state.outletIds : [],
                }, fmt],
            );
            await this.action.doAction(action);
        } catch (e) {
            console.error("export failed", e);
            const msg =
                (e && e.message && e.message.data && e.message.data.message) ||
                (e && e.message) || "Ekspor gagal.";
            this.state.errorText = msg;
            this.state.phase = "error";
        } finally {
            this.state.exporting = false;
        }
    }

    openAdvancedFilter() {
        // Q3 keputusan: minimal + tombol "Filter Lanjutan" → wizard native OCA
        // di dialog (posisi tetap: dashboard = quick view, native = advanced).
        // AFR: form wizard TransientModel; MIS: form mis.report.instance.
        const AFR_WIZARD_MODEL = {
            trial_balance: "trial.balance.report.wizard",
            general_ledger: "general.ledger.report.wizard",
            aged_partner: "aged.partner.balance.report.wizard",
            vat: "vat.report.wizard",
            open_items: "open.items.report.wizard",
            journal_ledger: "journal.ledger.report.wizard",
        };
        const action = this.activeReportConfig.engine === "MIS Builder"
            ? {
                type: "ir.actions.act_window",
                res_model: "mis.report.instance",
                views: [[false, "form"]],
                target: "current",
            }
            : {
                type: "ir.actions.act_window",
                res_model: AFR_WIZARD_MODEL[this.state.activeReport],
                views: [[false, "form"]],
                target: "new",
                context: {
                    // Pre-fill periode dari shell agar wizard terbuka siap pakai
                    default_date_from: this.period.date_from,
                    default_date_to: this.period.date_to,
                    default_date_at: this.period.date_to,
                },
            };
        this.action.doAction(action);
    }

    retry() {
        this.load();
    }

    backToDashboard() {
        this.action.doAction("geprekyukss_dashboard.action_geprekyukss_dashboard");
    }
}

// Register sebagai client action terpisah — menuju dari sidebar dashboard.
registry.category("actions").add("geprekyukss_dashboard.reports", GkReportPage);
