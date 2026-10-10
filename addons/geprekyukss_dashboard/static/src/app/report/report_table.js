/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * <ReportTable> — renderer tabel untuk laporan AFR (F1, roadmap §B.4).
 *
 * Props:
 *   columns : [{key, label, align: "left"|"right", format: "currency"|null,
 *               sortable, searchable}]
 *   rows    : [{<key>: value, ..., style?: "muted"|"total"}]
 *   meta    : optional {totals?: [{label, debit, credit}], ...}
 *
 * Fitur bawaan (roadmap §B.4): search substring (kolom searchable),
 * sort klik header (kolom sortable), paging klien (50 baris/halaman).
 * Tidak fetch sendiri — data dari parent (ReportShell).
 *
 * F3 (GL & VAT):
 *  - baris `style: "muted"|"total"` dirender italic/tebal (Saldo Awal/Akhir,
 *    sub-detail pajak) — sorting/search tetap bekerja (baris ikut aliran).
 *  - footer totals dari meta.totals (Σ engine AFR, bukan sum client-side).
 *
 * C1 (audit): mode SERVER-SIDE opsional (props.serverMode). Bila aktif,
 * pencarian/sorting/paging dikerjakan server (payload hanya 1 halaman);
 * bila tidak, perilaku lama (semua baris dimuat, filter di klien) tetap.
 *
 * Format angka: formatRp() diimpor dari dashboard.js (satu sumber,
 * sudah dipakai 4 tab existing).
 */
import { formatRp } from "../dashboard/dashboard.js";

const PAGE_SIZE = 50;

export class ReportTable extends Component {
    static template = "geprekyukss_dashboard.ReportTable";
    static props = {
        columns: { type: Array, element: Object },
        rows: { type: Array, element: Object },
        meta: { type: Object, optional: true },
        // C1: mode paginasi server-side (dikelola ReportShell).
        serverMode: { type: Boolean, optional: true },
        query: { type: Object, optional: true },
        onPage: { type: Function, optional: true },
        onQuery: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            search: "",
            sortKey: null,
            sortDir: "asc",
            page: 0,
        });
        this.formatRp = formatRp;
    }

    // --------------------------------------------------------------
    // C1 — abstraksi mode klien vs server.
    // --------------------------------------------------------------
    get serverMode() {
        return !!this.props.serverMode;
    }

    get pageSize() {
        return (this.props.meta && this.props.meta.limit) || PAGE_SIZE;
    }

    get currentPage() {
        return this.serverMode ? (this.props.query && this.props.query.page) || 0 : this.state.page;
    }

    get currentSearch() {
        return this.serverMode ? (this.props.query && this.props.query.search) || "" : this.state.search;
    }

    get currentSortKey() {
        return this.serverMode ? (this.props.query && this.props.query.sortKey) || null : this.state.sortKey;
    }

    get currentSortDir() {
        return this.serverMode ? (this.props.query && this.props.query.sortDir) || "asc" : this.state.sortDir;
    }

    // --------------------------------------------------------------
    // F7 — reskin tabel gaya FinanceFlow (foto 01 Riwayat Transaksi):
    // warna arah (debit merah / kredit hijau), chip sisi kolom D/K,
    // "–" utk sel nol. Murni presentasional — nilai & urutan tak berubah.
    // --------------------------------------------------------------
    /** Kelas warna utk sel currency: minus → merah, plus → hijau bila
     *  kolomnya kolom arah (debit/kredit/bucket), netral utk lainnya. */
    amountCls(col, value) {
        if (col.format !== "currency") return "";
        const v = Number(value) || 0;
        if (Math.abs(v) < 0.005) return " is-zero";
        const sideCols = new Set(["debit", "credit"]);
        if (sideCols.has(col.key)) {
            return col.key === "debit"
                ? (v < 0 ? " is-neg" : " is-debit")
                : (v < 0 ? " is-neg" : " is-credit");
        }
        return v < 0 ? " is-neg" : "";
    }

    /** Tampilkan "–" utk nol persis (gaya FinanceFlow), angka selain itu. */
    amountText(col, value) {
        if (col.format !== "currency") return value;
        const v = Number(value) || 0;
        return Math.abs(v) < 0.005 ? "–" : this.formatRp(value);
    }

    get filteredRows() {
        // C1: server sudah menyaring/mengurut/memotong.
        if (this.serverMode) return this.props.rows;
        const q = this.state.search.trim().toLowerCase();
        let rows = this.props.rows;
        if (q) {
            const searchable = this.props.columns.filter((c) => c.searchable).map((c) => c.key);
            rows = rows.filter((row) =>
                searchable.some((k) => String(row[k] ?? "").toLowerCase().includes(q))
            );
        }
        if (this.state.sortKey) {
            const key = this.state.sortKey;
            const dir = this.state.sortDir === "asc" ? 1 : -1;
            const isNum = this.props.columns.some(
                (c) => c.key === key && c.format === "currency"
            );
            rows = [...rows].sort((a, b) => {
                const va = a[key], vb = b[key];
                if (isNum) {
                    return ((Number(va) || 0) - (Number(vb) || 0)) * dir;
                }
                return String(va ?? "").localeCompare(String(vb ?? ""), "id") * dir;
            });
        }
        return rows;
    }

    // Footer totals — dari meta (engine AFR), bukan sum client-side.
    // Dua shape (F3/F6):
    //   debit/credit : GL & VAT (2 angka per baris footer)
    //   columns/values : Aged Partner (total per bucket — kolom arbitrer)
    // Baris all-zero disembunyikan (bulan kosong → footer "0" tidak berguna).
    get totalRows() {
        const totals = (this.props.meta && this.props.meta.totals) || [];
        const isZero = (v) => !Number(v);
        return totals.filter((t) =>
            t.values
                ? Object.values(t.values).some((v) => !isZero(v))
                : !(isZero(t.debit) && isZero(t.credit))
        );
    }

    get hasTotals() {
        return this.totalRows.length > 0;
    }

    get pageCount() {
        if (this.serverMode) {
            const total = (this.props.meta && this.props.meta.total_rows) || 0;
            return Math.max(1, Math.ceil(total / this.pageSize));
        }
        return Math.max(1, Math.ceil(this.filteredRows.length / PAGE_SIZE));
    }

    get pageRows() {
        if (this.serverMode) return this.props.rows;
        const start = this.state.page * PAGE_SIZE;
        return this.filteredRows.slice(start, start + PAGE_SIZE);
    }

    get rangeLabel() {
        if (this.serverMode) {
            const meta = this.props.meta || {};
            const total = meta.total_rows || 0;
            if (!total) return "0 baris";
            const offset = meta.offset || 0;
            const start = offset + 1;
            const end = Math.min(offset + this.pageSize, total);
            return `${start}–${end} dari ${total} baris`;
        }
        const total = this.filteredRows.length;
        if (!total) return "0 baris";
        const start = this.state.page * PAGE_SIZE + 1;
        const end = Math.min(start + PAGE_SIZE - 1, total);
        return `${start}–${end} dari ${total} baris`;
    }

    onSearch(ev) {
        const value = ev.target.value;
        if (this.serverMode) {
            this.props.onQuery && this.props.onQuery({ search: value });
            return;
        }
        this.state.search = value;
        this.state.page = 0;
    }

    onHeaderKeydown(ev, key) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.onSort(key);
        }
    }

    onSort(key) {
        const col = this.props.columns.find((c) => c.key === key);
        if (!col || !col.sortable) return;
        let sortDir;
        if (this.currentSortKey === key) {
            sortDir = this.currentSortDir === "asc" ? "desc" : "asc";
        } else {
            sortDir = "asc";
        }
        if (this.serverMode) {
            this.props.onQuery && this.props.onQuery({ sortKey: key, sortDir });
            return;
        }
        this.state.sortKey = key;
        this.state.sortDir = sortDir;
    }

    prevPage() {
        if (this.currentPage <= 0) return;
        if (this.serverMode) {
            this.props.onPage && this.props.onPage(this.currentPage - 1);
            return;
        }
        this.state.page -= 1;
    }

    nextPage() {
        if (this.currentPage >= this.pageCount - 1) return;
        if (this.serverMode) {
            this.props.onPage && this.props.onPage(this.currentPage + 1);
            return;
        }
        this.state.page += 1;
    }

    sortIcon(key) {
        if (this.currentSortKey !== key) return "fa-sort";
        return this.currentSortDir === "asc" ? "fa-sort-asc" : "fa-sort-desc";
    }
}
