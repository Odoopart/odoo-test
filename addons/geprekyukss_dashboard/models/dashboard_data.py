# -*- coding: utf-8 -*-
"""
geprekyukss.dashboard.data — Data layer dashboard (LIVE, parametrik bulan).

Prinsip:
- READ-ONLY untuk data bisnis (search_read / _read_group / search_count); P&L
  headline didelegasikan ke engine MIS Builder via compute() resmi (kanonik Q1
  opsi a — satu sumber kebenaran dengan laporan Laba Rugi di shell; wrapper
  hanya men-set kolom periode instance).
- Semua method menerima date_from & date_to ('YYYY-MM-DD', inklusif) → laporan live.
- Bulan tanpa data → has_data False / nilai 0 / vs None → frontend menampilkan placeholder.
- Angka wajib selaras laporan resmi (P&L, neraca) — diverifikasi via script Bagian C.
"""
from collections import defaultdict
from datetime import date, timedelta

from odoo import api, models

from .category_map import KATEGORI as PRODUCT_KATEGORI, get_category as get_product_category

# Kategori channel berdasar partner platform
PLATFORM_KEYWORDS = ("gofood", "grabfood", "shopeefood")


class GkDashboardData(models.AbstractModel):
    _name = "geprekyukss.dashboard.data"
    _description = "Sumber data Dashboard Keuangan Geprekyukss"

    POS_SALE_STATES = ["done", "invoiced", "posted", "paid"]
    EXPENSE_TYPES = ["expense", "expense_direct_cost", "expense_depreciation", "expense_gnrl_admin"]
    ASSET_TYPES = ["asset_cash", "asset_receivable", "asset_current", "asset_prepayments", "asset_fixed"]
    LIAB_TYPES = ["liability_payable", "liability_current"]
    EQUITY_TYPES = ["equity", "equity_unaffected"]

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, date_from, date_to, outlet_ids=None):
        """Payload lengkap 4 tab. date_from/date_to 'YYYY-MM-DD' inklusif.

        outlet_ids:
            - None / [] / [0] = "Semua Outlet" (default; tidak ada filter)
            - [int, ...]        = daftar pos.config.id yang di-include
        Filter diterapkan ke query POS-based (Tab 1, Tab 3). Tab 2 (akunting
        konsolidasi) & Tab 4 (aset/gudang) tidak ter-filter karena tidak
        linked ke pos.config di build ini — angka consolidated by design.
        Bila outlet difilter, payload menyertakan `outlet_contribution`
        (estimasi kontribusi POS-based — lihat _outlet_contribution).
        """
        d1 = date.fromisoformat(date_from)
        d2 = date.fromisoformat(date_to)
        prev_to = d1 - timedelta(days=1)
        prev_from = prev_to - timedelta(days=(d2 - d1).days)
        prev_from_s, prev_to_s = prev_from.isoformat(), prev_to.isoformat()

        # Normalisasi outlet_ids: None/[]/False → None (penanda "semua")
        clean_outlet_ids = self._normalize_outlet_ids(outlet_ids)

        res = {
            "period": {"date_from": date_from, "date_to": date_to},
            "prev_period": {"date_from": prev_from_s, "date_to": prev_to_s},
            "has_data": False,
            "outlet_filter": self._outlet_filter_meta(clean_outlet_ids),
        }

        summary = self._pos_sales_summary(date_from, date_to, clean_outlet_ids)
        prev_summary = self._pos_sales_summary(prev_from_s, prev_to_s, clean_outlet_ids)
        finance = self._finance_detail(date_from, date_to)
        # Sparkline kartu KPI (Redesign PowerBI Stage 1): laba bersih per hari.
        finance["daily_net_profit"] = self._align_daily(
            date_from, date_to, self._net_income_by_day(date_from, date_to))
        sales = self._sales_menu(date_from, date_to, clean_outlet_ids)
        ops = self._ops_warehouse(date_from, date_to)

        # Naratif butuh pembanding prev — kanonik (Q1a): dari compute MIS bulan sebelumnya
        fin_prev = self._mis_pl_headline_from_cells(self._mis_pl_cells(prev_from_s, prev_to_s))
        finance["net_profit_prev"] = fin_prev["net_profit"]
        finance["hpp_prev"] = fin_prev["hpp_total"]

        res["has_data"] = (
            summary["order_count"] > 0
            or finance["activity_lines"] > 0
            or sales["order_count"] > 0
        )

        summary["vs"] = self._compute_vs(summary, prev_summary)
        res["summary"] = summary
        res["summary_prev"] = prev_summary
        res["finance"] = finance
        res["sales"] = sales
        res["ops"] = ops
        # Beranda PSAK hero (F1) — 5 KPI + tren + kas/settlement + arus PSAK + neraca + kepatuhan + laba bulanan
        try:
            res["beranda"] = self._beranda_detail(
                date_from, date_to, clean_outlet_ids, finance, fin_prev, summary, sales, ops,
                prev_from_s, prev_to_s,
            )
        except Exception as e:  # fail-soft: dashboard tetap jalan
            import logging
            logging.getLogger(__name__).warning("beranda detail failed: %s", e, exc_info=True)
            res["beranda"] = self._beranda_fallback(finance, fin_prev, summary, sales, ops, date_from, date_to)
        # Kontribusi outlet (keputusan 12 Sep): P&L konsolidasi by design (GL tanpa
        # dimensi outlet). Saat outlet difilter, tambahkan estimasi kontribusi
        # POS-based: omzet exact (pos.order) − HPP (qty × standard_cost produk).
        # Semua-outlet → field tidak ada (frontend pakai P&L konsolidasi).
        if clean_outlet_ids:
            res["outlet_contribution"] = self._outlet_contribution(
                date_from, date_to, clean_outlet_ids, summary)
        # Tab Pajak — PBJT (Pajak Daerah F&B) per outlet (modul geprekyukss_pbjt).
        try:
            res["pbjt"] = self._pbjt_summary(date_from, date_to, clean_outlet_ids)
        except Exception as e:  # fail-soft: dashboard tetap jalan
            import logging
            logging.getLogger(__name__).warning("pbjt summary failed: %s", e, exc_info=True)
            res["pbjt"] = None
        return res

    @api.model
    def list_available_outlets(self):
        """Dipakai frontend untuk mengisi dropdown filter outlet."""
        rows = self.env["pos.config"].search_read([], ["name"], order="name")
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    def _normalize_outlet_ids(self, outlet_ids):
        """None / [] / [0] / [None] → None (= semua outlet)."""
        if not outlet_ids:
            return None
        cleaned = [int(x) for x in outlet_ids if x]
        return cleaned or None

    def _outlet_filter_meta(self, clean_outlet_ids):
        """Echo balik ke frontend untuk display pill (mis. 'Pallangga + Mallengkeri')."""
        if not clean_outlet_ids:
            return {"id": "all", "name": "Semua Outlet", "ids": []}
        names = self.env["pos.config"].browse(clean_outlet_ids).mapped("name")
        return {
            "id": clean_outlet_ids[0] if len(clean_outlet_ids) == 1 else "multi",
            "name": " + ".join(names) if names else f"{len(clean_outlet_ids)} outlet",
            "ids": list(clean_outlet_ids),
        }

    # ------------------------------------------------------------------
    # KONTRIBUSI OUTLET (POS-based) — estimasi kontribusi P&L saat filter
    # outlet aktif. GL tidak punya dimensi outlet (build ini), jadi P&L
    # konsolidasi tidak bisa di-split per outlet. Estimasi = omzet exact
    # (pos.order) − HPP (qty pos.order.line × standard_cost produk).
    # Beban operasional (gaji, sewa, penyusutan) dicatat konsolidasi →
    # TIDAK diatribusikan; angka ini = kontribusi margin, bukan laba outlet.
    # ------------------------------------------------------------------
    def _outlet_contribution(self, date_from, date_to, outlet_ids, summary):
        Line = self.env["pos.order.line"]
        lines_data = Line.search_read(
            [("order_id", "in", self.env["pos.order"].search(
                self._pos_domain(date_from, date_to, outlet_ids)).ids)],
            ["product_id", "qty", "price_subtotal_incl"], limit=200000)
        cogs, n_lines = 0.0, len(lines_data)
        for l in lines_data:
            qty = l["qty"] or 0.0
            # FIX 15 Sep: Odoo 19 memakai `standard_price` (field jsonb company-
            # dependent di product.product); `standard_cost` = nama lama pra-v17
            # → AttributeError. Ini satu-satunya pemakaian `standard_cost`.
            cost = (l["product_id"] and
                    self.env["product.product"].browse(l["product_id"][0]).standard_price) or 0.0
            cogs += qty * (cost or 0.0)
        omzet = summary["amount_total"]
        return {
            "mode": "pos_estimate",
            "label": "Kontribusi Outlet",
            "omzet": omzet,
            "cogs_estimate": cogs,
            "gross_margin": omzet - cogs,
            "gross_margin_pct": (omzet - cogs) / omzet * 100.0 if omzet else 0.0,
            "lines_counted": n_lines,
        }

    # ------------------------------------------------------------------
    # TAB PAJAK — PBJT (Pajak Daerah F&B) per outlet
    # ------------------------------------------------------------------
    def _pbjt_summary(self, date_from, date_to, outlet_ids=None):
        Config = self.env["pbjt.outlet.config"]
        Recon = self.env["pbjt.reconciliation"]
        domain = [("active", "=", True)]
        if outlet_ids:
            domain.append(("pos_config_id", "in", outlet_ids))
        configs = Config.search(domain, order="pos_config_id")

        def _tax(gross, cfg):
            exempt = gross <= (cfg.exempt_omzet_month or 0.0)
            if exempt or not gross:
                return gross, 0.0, exempt
            if cfg.price_include:
                dpp = gross / (1.0 + (cfg.rate or 0.0) / 100.0)
                return dpp, gross - dpp, exempt
            return gross, gross * (cfg.rate or 0.0) / 100.0, exempt

        per_outlet = []
        totals = {"gross": 0.0, "dpp": 0.0, "real_tax": 0.0, "negotiated": 0.0, "gap": 0.0}
        for cfg in configs:
            rows = self.env["pos.order"]._read_group(
                self._pos_domain(date_from, date_to, [cfg.pos_config_id.id]),
                [], ["amount_total:sum"])
            gross = rows[0][0] if rows else 0.0
            dpp, tax, exempt = _tax(gross, cfg)
            recons = Recon.search([
                ("config_id", "=", cfg.id),
                ("date_from", ">=", date_from),
                ("date_to", "<=", date_to),
            ])
            negotiated = sum(recons.mapped("negotiated_amount"))
            per_outlet.append({
                "outlet_id": cfg.pos_config_id.id,
                "outlet": cfg.pos_config_id.name,
                "daerah": cfg.daerah,
                "perda_ref": cfg.perda_ref,
                "rate": cfg.rate,
                "price_include": cfg.price_include,
                "gross": gross,
                "dpp": dpp,
                "real_tax": tax,
                "negotiated": negotiated,
                "gap": tax - negotiated,
                "is_exempt": exempt,
            })
            totals["gross"] += gross
            totals["dpp"] += dpp
            totals["real_tax"] += tax
            totals["negotiated"] += negotiated
            totals["gap"] += tax - negotiated
        return {"per_outlet": per_outlet, "totals": totals, "config_count": len(configs)}

    # ------------------------------------------------------------------
    # TAB 1 — RINGKASAN EKSEKUTIF
    # ------------------------------------------------------------------
    def _pos_domain(self, date_from, date_to, outlet_ids=None):
        # F1 (audit GUI 26 Sep): `date_order` adalah DATETIME UTC. Batas string
        # 'YYYY-MM-DD' apa adanya di-konversi Odoo dari timezone user yang login,
        # sehingga rentang bergeser per pengguna (omzet POS berubah menurut tz).
        # Pakai datetime penuh "YYYY-MM-DD 00:00:00" agar diperlakukan sebagai
        # UTC apa adanya → identik dengan Pendapatan GL/MIS di semua tz.
        dom = [
            ("date_order", ">=", date_from + " 00:00:00"),
            ("date_order", "<", self._next_day(date_to) + " 00:00:00"),
            ("state", "in", self.POS_SALE_STATES),
        ]
        if outlet_ids:
            dom.append(("config_id", "in", outlet_ids))
        return dom

    def _pos_sales_summary(self, date_from, date_to, outlet_ids=None):
        dom = self._pos_domain(date_from, date_to, outlet_ids)
        # F1: grouping `date_order:day` juga harus UTC agar Σ harian == total
        # (domain sudah UTC; tanpa ini grouping mengikuti tz user → tak rekonsiliasi).
        Order = self.env["pos.order"].with_context(tz="UTC")

        rows = Order._read_group(dom, [], ["amount_total:sum"])
        total = rows[0][0] or 0.0 if rows else 0.0
        count = Order.search_count(dom)

        outlets = []
        for cfg, amount, cnt in Order._read_group(dom, ["config_id"], ["amount_total:sum", "id:count"]):
            outlets.append({
                "config_id": cfg.id,
                "name": cfg.name,
                "order_count": cnt or 0,
                "amount_total": amount or 0.0,
                "avg_ticket": (amount / cnt) if cnt else 0.0,
            })
        outlets.sort(key=lambda o: -o["amount_total"])

        daily_map = defaultdict(float)
        for dt, amount in Order._read_group(dom, ["date_order:day"], ["amount_total:sum"]):
            if dt:
                daily_map[dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]] = amount or 0.0
        # Sparkline kartu KPI (Redesign PowerBI Stage 1): order/hari → avg ticket/hari ikut terhitung.
        daily_orders_map = defaultdict(int)
        for dt, cnt in Order._read_group(dom, ["date_order:day"], ["id:count"]):
            if dt:
                daily_orders_map[dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]] = cnt or 0
        d1 = date.fromisoformat(date_from)
        d2 = date.fromisoformat(date_to)
        daily = []
        daily_orders = []
        daily_avg_ticket = []
        cur = d1
        while cur <= d2:
            key = cur.isoformat()
            amt = daily_map.get(key, 0.0)
            cnt = daily_orders_map.get(key, 0)
            daily.append({"date": key, "amount": amt})
            daily_orders.append({"date": key, "count": cnt})
            daily_avg_ticket.append({"date": key, "value": (amt / cnt) if cnt else 0.0, "count": cnt})
            cur += timedelta(days=1)

        return {
            "amount_total": total or 0.0,
            "order_count": count,
            "avg_ticket": (total / count) if count else 0.0,
            "avg_daily": (total / max(len(daily), 1)),
            "daily": daily,
            "daily_orders": daily_orders,
            "daily_avg_ticket": daily_avg_ticket,
            "outlets": outlets,
        }

    def _compute_vs(self, cur, prev):
        """Persen perubahan vs bulan lalu; None jika bulan lalu tanpa data → placeholder."""
        def pct(c, p):
            if not p:
                return None
            return round((c - p) / p * 100.0, 1)
        return {
            "amount_total": pct(cur["amount_total"], prev["amount_total"]),
            "order_count": pct(cur["order_count"], prev["order_count"]),
            "avg_ticket": pct(cur["avg_ticket"], prev["avg_ticket"]),
        }

    # ------------------------------------------------------------------
    # TAB 2 — DETAIL KEUANGAN
    # ------------------------------------------------------------------
    def _finance_detail(self, date_from, date_to):
        Aml = self.env["account.move.line"]
        # active_test=False: akun ARSIP (active=False) tetap punya saldo &
        # mutasi di buku besar (dihitung AFR juga) — tanpa ini, neraca Tab 2
        # timpang (temuan F2 cross-check 12 Sep 2026, selisih 10.390.981).
        Account = self.env["account.account"].with_context(active_test=False)

        # Kanonik Q1 opsi (a): headline P&L dari compute MIS Builder (template
        # mis_report_pl via wrapper — jalur yang sama dengan shell UI).
        # Satu compute menghasilkan kolom Bulan (idx 0) + YTD (idx 1).
        pl_cells = self._mis_pl_cells(date_from, date_to)
        pl = self._mis_pl_headline_from_cells(pl_cells)

        exp_accounts = Account.search([("account_type", "in", self.EXPENSE_TYPES)])
        dom_exp = [
            ("date", ">=", date_from), ("date", "<=", date_to),
            ("account_id", "in", exp_accounts.ids), ("parent_state", "=", "posted"),
        ]
        expenses, hpp_total, dep_total, commission = [], 0.0, 0.0, 0.0
        for acc, debit, credit in Aml._read_group(dom_exp, ["account_id"], ["debit:sum", "credit:sum"]):
            amt = (debit or 0.0) - (credit or 0.0)
            if abs(amt) < 0.01:
                continue
            # Redesign PowerBI Stage 3: kategori warna bar breakdown beban.
            # Akun penyusutan di build ini bertipe expense (bukan expense_depreciation)
            # → deteksi via nama, konsisten dgn dep_total di bawah.
            name_l = acc.name.lower()
            if acc.account_type == "expense_direct_cost":
                category = "hpp"
            elif "penyusutan" in name_l:
                category = "depreciation"
            else:
                category = "operational"
            expenses.append({"code": acc.code, "name": acc.name, "amount": amt,
                             "type": acc.account_type, "category": category})
            if acc.account_type == "expense_direct_cost":
                hpp_total += amt
            if "penyusutan" in acc.name.lower():
                dep_total += amt
            if "komisi" in acc.name.lower():
                commission += amt
        expenses.sort(key=lambda e: -e["amount"])

        # Arus kas: mutasi kas/bank bulan berjalan
        cash_accounts = Account.search([("account_type", "=", "asset_cash")])
        dom_cash = [
            ("date", ">=", date_from), ("date", "<=", date_to),
            ("account_id", "in", cash_accounts.ids), ("parent_state", "=", "posted"),
        ]
        cash_in = sum((r[1] or 0.0) for r in Aml._read_group(dom_cash, ["account_id"], ["debit:sum", "credit:sum"]))
        cash_out = sum((r[2] or 0.0) for r in Aml._read_group(dom_cash, ["account_id"], ["debit:sum", "credit:sum"]))

        # Posisi kas & bank (kumulatif s.d. akhir periode)
        positions = []
        for acc, debit, credit in Aml._read_group(
                [("account_id", "in", cash_accounts.ids), ("parent_state", "=", "posted"),
                 ("date", "<=", date_to)],
                ["account_id"], ["debit:sum", "credit:sum"]):
            bal = (debit or 0.0) - (credit or 0.0)
            if abs(bal) < 0.01:
                continue
            name_l = acc.name.lower()
            if "kas" in name_l:
                kind = "kas"
            elif any(w in name_l for w in ("qris", "ovo", "gopay", "go-pay", "shopee")):
                kind = "ewallet"
            else:
                kind = "bank"
            positions.append({"code": acc.code, "name": acc.name, "kind": kind, "balance": bal})
        positions.sort(key=lambda p: -p["balance"])

        # Neraca konsolidasi (kumulatif s.d. date_to)
        assets = self._net_of(Account, self.ASSET_TYPES, date_to, sign=1)
        liabilities = self._net_of(Account, self.LIAB_TYPES, date_to, sign=-1)
        equity = self._net_of(Account, self.EQUITY_TYPES, date_to, sign=-1)
        # NI YTD kanonik: kolom YTD (idx 1) dari compute MIS yang sama
        net_income_ytd = pl["net_profit_ytd"]

        # Piutang open
        inv = self.env["account.move"].search_read(
            [("move_type", "in", ["out_invoice", "out_refund"]), ("state", "=", "posted"),
             ("payment_state", "in", ["not_paid", "partial"])],
            ["name", "partner_id", "invoice_date_due", "amount_residual"],
            order="invoice_date_due", limit=50)
        receivables = [{
            "name": r["name"], "partner": r["partner_id"][1] if r["partner_id"] else "-",
            "due": r["invoice_date_due"], "residual": r["amount_residual"],
        } for r in inv]

        activity = Aml.search_count(
            [("date", ">=", date_from), ("date", "<=", date_to), ("parent_state", "=", "posted")])

        return {
            "expenses": expenses,
            # Headline = compute MIS (kanonik); breakdown expenses di atas tetap
            # agregasi raw per akun (presentasional, kategori warna UI).
            "expense_total": pl["expense_total"],
            "hpp_total": pl["hpp_total"],
            "depreciation_total": pl["depreciation_total"],
            "platform_commission": commission,
            "income_total": pl["income_total"],
            "net_profit": pl["net_profit"],
            "net_profit_ytd": pl["net_profit_ytd"],
            "cashflow": {"in": cash_in, "out": cash_out, "net": cash_in - cash_out},
            "cash_positions": positions,
            "balance": {
                "total_assets": assets,
                "total_liab_equity": liabilities + equity + net_income_ytd,
                "liabilities": liabilities,
                "equity": equity,
                "net_income_ytd": net_income_ytd,
            },
            "receivables": {"total": sum(r["residual"] for r in receivables), "list": receivables},
            "activity_lines": activity,
        }

    def _net_of(self, Account, types, date_to, sign):
        accs = Account.search([("account_type", "in", types)])
        total = 0.0
        for acc, debit, credit in self.env["account.move.line"]._read_group(
                [("account_id", "in", accs.ids), ("parent_state", "=", "posted"), ("date", "<=", date_to)],
                ["account_id"], ["debit:sum", "credit:sum"]):
            total += ((debit or 0.0) - (credit or 0.0)) * sign
        return total

    # ------------------------------------------------------------------
    # KANONIK P&L (Q1 opsi a) — compute MIS Builder via wrapper resmi
    # ------------------------------------------------------------------
    def _mis_pl_cells(self, date_from, date_to):
        """Payload get_report_data('profit_loss_mis') utk window date_from..date_to.
        Wrapper menyinkronkan 2 kolom fix: Bulan (idx 0) + YTD (idx 1), lalu
        menjalankan compute() resmi mis.report.instance (engine OCA)."""
        return self.env["geprekyukss.dashboard.report.actions"].get_report_data(
            "profit_loss_mis", {"date_from": date_from, "date_to": date_to, "outlet_ids": []})

    def _mis_pl_headline_from_cells(self, payload):
        """Ekstrak headline P&L dari payload matrix MIS (baris di-key by label).
        Sel kosong (AccountingNone) ≡ 0 — konvensi yang sama dgn test parity."""
        vals = {}
        for row in payload["body"]:
            cells = row["cells"]
            vals[row["label"]] = [
                (cells[i]["val"] or 0.0) if i < len(cells) else 0.0
                for i in (0, 1)
            ]
        month, ytd = 0, 1
        return {
            "income_total": vals.get("PENDAPATAN", [0.0, 0.0])[month],
            "expense_total": vals.get("BEBAN", [0.0, 0.0])[month],
            "hpp_total": vals.get("HPP (Harga Pokok Penjualan)", [0.0, 0.0])[month],
            "depreciation_total": vals.get("Beban Penyusutan", [0.0, 0.0])[month],
            "net_profit": vals.get("LABA BERSIH", [0.0, 0.0])[month],
            "net_profit_ytd": vals.get("LABA BERSIH", [0.0, 0.0])[ytd],
        }


    def _align_daily(self, date_from, date_to, value_map, value_key="value"):
        """Align map{'YYYY-MM-DD': v} → [{date, <value_key>}] inklusif; hari kosong = 0."""
        d1, d2 = date.fromisoformat(date_from), date.fromisoformat(date_to)
        out, cur = [], d1
        while cur <= d2:
            key = cur.isoformat()
            out.append({"date": key, value_key: value_map.get(key, 0.0)})
            cur += timedelta(days=1)
        return out

    def _net_income_by_day(self, date_from, date_to):
        """Map {'YYYY-MM-DD': net} laba bersih per hari — kanonik: sisa (net − Σ hari)
        diletakkan di tanggal date_to (deterministik, konsisten dgn agregasi GL)."""
        # active_test=False: akun ARSIP (active=False) tetap punya saldo &
        # mutasi di buku besar (dihitung AFR juga) — konsisten dgn engine MIS.
        Account = self.env["account.account"].with_context(active_test=False)
        Aml = self.env["account.move.line"]
        income_accs = Account.search([("account_type", "in", ["income", "income_other"])])
        expense_accs = Account.search([("account_type", "in", self.EXPENSE_TYPES)])
        dom_base = [("date", ">=", date_from), ("date", "<=", date_to), ("parent_state", "=", "posted")]

        def _day_key(dt):
            return dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]

        d2 = date.fromisoformat(date_to)
        by_day = defaultdict(float)
        for dt, debit, credit in Aml._read_group(
                dom_base + [("account_id", "in", income_accs.ids)],
                ["date:day"], ["debit:sum", "credit:sum"]):
            if dt:
                by_day[_day_key(dt)] += (credit or 0.0) - (debit or 0.0)
        for dt, debit, credit in Aml._read_group(
                dom_base + [("account_id", "in", expense_accs.ids)],
                ["date:day"], ["debit:sum", "credit:sum"]):
            if dt:
                by_day[_day_key(dt)] -= (debit or 0.0) - (credit or 0.0)

        # Kanonik: sisa (net MIS − Σ hari) diletakkan di tanggal date_to
        # (deterministik, konsisten dgn headline & agregasi GL)
        net = self._finance_detail(date_from, date_to)["net_profit"]
        residual = net - sum(by_day.values())
        if abs(residual) >= 0.01:
            by_day[_day_key(d2)] += residual
        return by_day


    # ------------------------------------------------------------------
    # TAB 3 — PENJUALAN & CHANNEL
    # ------------------------------------------------------------------
    def _sales_menu(self, date_from, date_to, outlet_ids=None):
        Order = self.env["pos.order"]
        Line = self.env["pos.order.line"]
        dom = self._pos_domain(date_from, date_to, outlet_ids)
        orders = Order.search(dom)
        order_ids = orders.ids

        # Top produk (qty & omzet)
        prod_map = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
        lines_data = Line.search_read([("order_id", "in", order_ids)],
                                      ["product_id", "qty", "price_subtotal_incl"], limit=200000)
        for l in lines_data:
            pid = l["product_id"][0] if l["product_id"] else 0
            pname = l["product_id"][1] if l["product_id"] else "?"
            m = prod_map[pid]
            m["name"] = pname
            m["qty"] += l["qty"] or 0.0
            m["amount"] += l["price_subtotal_incl"] or 0.0
        top_by_amount = sorted(prod_map.values(), key=lambda x: -x["amount"])[:10]
        top_by_qty = sorted(prod_map.values(), key=lambda x: -x["qty"])[:10]

        # Channel dari partner platform
        ch_map = defaultdict(lambda: {"order_count": 0, "amount": 0.0})
        for o in orders.read(["partner_id", "amount_total"]):
            pname = (o["partner_id"][1].lower() if o["partner_id"] else "Dine-in / Walk-in")
            if any(k in pname for k in PLATFORM_KEYWORDS):
                ch_name = o["partner_id"][1].replace(" Platform", "").title()
            else:
                ch_name = "Dine-in / Walk-in"
            c = ch_map[ch_name]
            c["order_count"] += 1
            c["amount"] += o["amount_total"] or 0.0
        total_amount = sum(c["amount"] for c in ch_map.values()) or 1.0
        channels = [{"name": k, **v, "pct": round(v["amount"] / total_amount * 100.0, 1)}
                    for k, v in ch_map.items()]
        channels.sort(key=lambda c: -c["amount"])

        # Metode pembayaran
        # Redesign PowerBI Stage 3: grup warna bar metode pembayaran
        # (qris/cash/ewallet/card) — dipakai frontend via gkPaymentColor().
        def _payment_group(name):
            n = (name or "").lower()
            if "qris" in n:
                return "qris"
            if "tunai" in n or "cash" in n:
                return "cash"
            if any(k in n for k in ("shopeepay", "go-pay", "gopay", "ovo", "dana")):
                return "ewallet"
            if "kartu" in n or any(b in n for b in ("bca", "bni", "bri", "mandiri")):
                return "card"
            return "other"

        payments = []
        for pm, amount, cnt in self.env["pos.payment"]._read_group(
                [("pos_order_id", "in", order_ids)], ["payment_method_id"],
                ["amount:sum", "id:count"]):
            payments.append({"name": pm.name, "amount": amount or 0.0, "order_count": cnt or 0,
                             "group": _payment_group(pm.name)})
        payments.sort(key=lambda p: -p["amount"])

        # Per outlet
        outlets = []
        for cfg, amount, cnt in Order._read_group(dom, ["config_id"], ["amount_total:sum", "id:count"]):
            outlets.append({
                "config_id": cfg.id, "name": cfg.name,
                "amount_total": amount or 0.0, "order_count": cnt or 0,
                "avg_ticket": (amount / cnt) if cnt else 0.0,
            })
        outlets.sort(key=lambda o: -o["amount_total"])

        n_days = max(1, (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1)
        return {
            "order_count": len(order_ids),
            "amount_total": sum(o["amount_total"] or 0.0 for o in orders.read(["amount_total"])),
            "avg_daily_orders": round(len(order_ids) / n_days, 1),
            "top_by_amount": top_by_amount,
            "top_by_qty": top_by_qty,
            "channels": channels,
            "payments": payments,
            "outlets": outlets,
        }

    # ------------------------------------------------------------------
    # TAB 4 — ASET & OPERASIONAL
    # ------------------------------------------------------------------
    def _ops_warehouse(self, date_from, date_to):
        # active_test=False: akun ARSIP (active=False) tetap punya saldo &
        # mutasi di buku besar (dihitung AFR juga) — tanpa ini, neraca Tab 2
        # timpang (temuan F2 cross-check 12 Sep 2026, selisih 10.390.981).
        Account = self.env["account.account"].with_context(active_test=False)
        Aml = self.env["account.move.line"]

        # --- Aset tetap: akun aset (gross) + akumulasi + penyusutan bulan ini
        fa_accounts = Account.search([("account_type", "=", "asset_fixed")])
        rows_by_code = {}
        accum_by_name = {}
        for acc, debit, credit in Aml._read_group(
                [("account_id", "in", fa_accounts.ids), ("parent_state", "=", "posted"), ("date", "<=", date_to)],
                ["account_id"], ["debit:sum", "credit:sum"]):
            bal = (debit or 0.0) - (credit or 0.0)
            if abs(bal) < 0.01:
                continue
            name_l = acc.name.lower()
            if "akumulasi" in name_l:
                # "Akumulasi Penyusutan Kendaraan" → join ke aset "Kendaraan" via nama
                bare = acc.name
                for prefix in ("Akumulasi Penyusutan ", "Akumulasi penyusutan ", "Akum. Penyusutan "):
                    if bare.startswith(prefix):
                        bare = bare[len(prefix):]
                        break
                accum_by_name[bare.strip().lower()] = accum_by_name.get(bare.strip().lower(), 0.0) - bal
            else:
                target = rows_by_code.setdefault(acc.code, {})
                target.update({"code": acc.code, "name": acc.name, "gross": bal, "accum": target.get("accum", 0.0)})

        # Penyusutan bulan berjalan per akun beban penyusutan
        dep_accounts = Account.search([("account_type", "in", self.EXPENSE_TYPES)])
        dep_by_name = {}
        for acc, debit, credit in Aml._read_group(
                [("date", ">=", date_from), ("date", "<=", date_to),
                 ("account_id", "in", dep_accounts.ids), ("parent_state", "=", "posted")],
                ["account_id"], ["debit:sum", "credit:sum"]):
            if "penyusutan" in acc.name.lower() and (debit or 0.0) > 0:
                dep_by_name[acc.name] = dep_by_name.get(acc.name, 0.0) + debit

        # Penyusutan per bulan diambil dari JADWAL REGISTER OCA — sumber yang sama dipakai
        # kartu "Jadwal Penyusutan Mendatang" dan test F4. Sebelum P7 (19 Sep 2026) angka
        # diambil dari total beban GL sepanjang periode laporan, sehingga kolom
        # "Penyusutan/Bulan" tampil 3x lipat (Resto Rp 7.165.003,34 padahal
        # Rp 3.027.466,20/bulan) dan "Masa Manfaat" ikut salah (5,8 thn padahal 13,8 thn).
        # Aset yang belum/bukan di register memakai cadangan: beban GL / jumlah bulan periode.
        _d1 = date.fromisoformat(str(date_from)[:10])
        _d2 = date.fromisoformat(str(date_to)[:10])
        n_bulan = max(1, (_d2.year - _d1.year) * 12 + (_d2.month - _d1.month) + 1)
        jadwal_berikut = {}
        try:
            for ln in self.env["account.asset.line"].search([
                    ("type", "=", "depreciate"), ("init_entry", "=", False),
                    ("move_check", "=", False), ("line_date", ">", date_to)], order="line_date"):
                akun_bruto = ln.asset_id.profile_id.account_asset_id or ln.asset_id["account_asset_id"]
                if not akun_bruto:
                    continue
                bulan = ln.line_date.strftime("%Y-%m")
                per_akun = jadwal_berikut.setdefault(akun_bruto.code, {})
                per_akun[bulan] = per_akun.get(bulan, 0.0) + (ln.amount or 0.0)
        except Exception:      # modul aset belum terpasang / register kosong
            jadwal_berikut = {}

        asset_rows = []
        total_gross = total_accum = total_dep_month = 0.0
        for code, t in rows_by_code.items():
            gross = t.get("gross", 0.0)
            if gross <= 0:
                continue
            accum = accum_by_name.get(t["name"].strip().lower(), 0.0)
            dep_period = self._match_dep_month(t["name"], dep_by_name)
            bulan_reg = jadwal_berikut.get(code) or {}
            if bulan_reg:
                dep_month = bulan_reg[sorted(bulan_reg)[0]]      # bulan pertama yang dijadwalkan
            else:
                dep_month = dep_period / n_bulan
            life = round(gross / dep_month / 12.0, 1) if dep_month else None
            asset_rows.append({
                "code": code, "name": t["name"], "gross": gross,
                "accum": accum, "net": gross - accum,
                "dep_month": dep_month, "dep_period": dep_period,
                "dep_source": "register" if bulan_reg else "gl",
                "life_years": life,
            })
            total_gross += gross
            total_accum += accum
            total_dep_month += dep_month
        asset_rows.sort(key=lambda r: -r["gross"])

        # --- Jadwal penyusutan mendatang dari register OCA (F4, 15 Sep 2026) ---
        # Sebelum F4 tidak ada satu pun baris di `account.asset`, sehingga panel
        # "Jadwal Penyusutan Mendatang" hanya placeholder. Kini jadwalnya dibaca
        # dari `account.asset.line` (baris terjadwal yang belum diposting),
        # diagregasi per bulan untuk 12 bulan pertama setelah `date_to`.
        schedule = []
        try:
            lines = self.env["account.asset.line"].search([
                ("type", "=", "depreciate"),
                ("init_entry", "=", False),
                ("move_check", "=", False),
                ("line_date", ">", date_to),
            ], order="line_date")
            buckets = {}
            for ln in lines:
                key = ln.line_date.strftime("%Y-%m")
                bucket = buckets.setdefault(key, {"amount": 0.0, "assets": set()})
                bucket["amount"] += ln.amount or 0.0
                bucket["assets"].add(ln.asset_id.id)
            bulan = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                     "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
            for key in sorted(buckets)[:12]:
                y, m = key.split("-")
                b = buckets[key]
                schedule.append({
                    "month": key,
                    "label": "%s %s" % (bulan[int(m) - 1], y),
                    "amount": b["amount"],
                    "count": len(b["assets"]),
                })
        except Exception:      # modul aset belum terpasang → panel kosong
            schedule = []

        # --- Persediaan per gudang
        wh_rows, inv_total = [], 0.0
        for wh in self.env["stock.warehouse"].search([]):
            loc = wh.lot_stock_id
            q = self.env["stock.quant"]._read_group(
                [("location_id", "child_of", loc.id)], [], ["value:sum", "quantity:sum"])
            val = (q[0][0] or 0.0) if q else 0.0
            qty = (q[0][1] or 0.0) if q else 0.0
            wh_rows.append({"warehouse": wh.name, "value": val, "qty": qty})
            inv_total += val

        # --- Waste / susut: scrap selesai dalam periode
        # A3 (audit): stock.scrap Odoo 19 TIDAK punya field scrap_value, jadi
        # `getattr(s, "scrap_value", 0.0)` selalu 0 → panel waste kosong walau
        # ada scrap. Nilai dihitung dari stock.valuation.layer (bila modul
        # valuasi ada) atau fallback qty × standard_price.
        Scrap = self.env["stock.scrap"]
        scraps = []
        try:
            for s in Scrap.search([("date_done", ">=", date_from), ("date_done", "<=", self._next_day(date_to)),
                                   ("state", "=", "done")], limit=100):
                scraps.append({"product": s.product_id.name, "qty": s.scrap_qty,
                               "value": self._scrap_value(s)})
        except Exception:
            pass
        waste_total = sum(s["value"] for s in scraps) if scraps else 0.0

        return {
            "assets": {
                "rows": asset_rows,
                "total_gross": total_gross,
                "total_accum": total_accum,
                "total_net": total_gross - total_accum,
                "total_dep_month": total_dep_month,
                "schedule": schedule,
                "schedule_total": sum(s["amount"] for s in schedule),
                "schedule_next": schedule[0]["label"] if schedule else None,
            },
            "inventory": {"per_warehouse": wh_rows, "total": inv_total},
            "waste": {"count": len(scraps), "total_value": waste_total, "rows": scraps},
        }

    def _scrap_value(self, scrap):
        """Nilai susut satu scrap (A3).

        Prioritas: Σ |stock.valuation.layer.value| dari pergerakan scrap
        (nilai persediaan sesungguhnya, modul valuasi aktif). Fallback:
        scrap_qty × product.standard_price. Selalu nilai absolut (scrap =
        arus keluar persediaan yang value-nya negatif di SVL).
        """
        qty = abs(scrap.scrap_qty or 0.0)
        try:
            moves = scrap.move_ids
            if moves and "stock.valuation.layer" in self.env:
                svls = self.env["stock.valuation.layer"].search(
                    [("stock_move_id", "in", moves.ids)])
                total = sum(abs(v.value or 0.0) for v in svls)
                if total:
                    return total
        except Exception:
            pass
        return qty * (getattr(scrap.product_id, "standard_price", 0.0) or 0.0)

    def _match_dep_month(self, asset_name, dep_by_name):
        # "Aset Renovasi" ↔ "Beban Penyusutan Renovasi"; fallback: kata kunci
        key = asset_name.lower()
        for name, amt in dep_by_name.items():
            n = name.lower().replace("beban penyusutan", "").strip()
            if n and n in key:
                return amt
        # fallback kata kunci (mis. "Peralatan Resto" → "Resto")
        words = [w for w in key.replace("aset", "").split() if len(w) > 3]
        for name, amt in dep_by_name.items():
            if any(w in name.lower() for w in words):
                return amt
        return 0.0

    # ------------------------------------------------------------------
    # BERANDA PSAK HERO (F1) — 5 KPI + tren + kas/settlement + arus PSAK +
    # snapshot neraca + kepatuhan + laba bulanan. Semua angka kanonik
    # (P&L via MIS, neraca via _net_of, pendapatan harian via GL).
    # ------------------------------------------------------------------
    def _kategori_produk_detail(self, date_from, date_to, outlet_ids=None):
        """Omzet per 5 kategori produk (donut Beranda, K3b-rev 15 Sep).

        Sumber: pos.order.line periode aktif (domain & filter outlet sama
        dengan omzet headline) → dipetakan via data/category_map.json
        (fallback rule-based di category_map.py). Basis amount =
        price_subtotal_incl agar Σ == summary.amount_total (recon test).
        """
        Line = self.env["pos.order.line"]
        order_ids = self.env["pos.order"].search(
            self._pos_domain(date_from, date_to, outlet_ids)).ids
        if not order_ids:
            return []
        lines = Line.search_read(
            [("order_id", "in", order_ids)],
            ["product_id", "price_subtotal_incl"], limit=200000)
        cat_amount = defaultdict(float)
        for l in lines:
            pname = l["product_id"][1] if l["product_id"] else "?"
            cat_amount[get_product_category(pname)] += l["price_subtotal_incl"] or 0.0
        total = sum(cat_amount.values()) or 1.0
        rows = [
            {"name": k, "amount": cat_amount.get(k, 0.0),
             "pct": round(cat_amount.get(k, 0.0) / total * 100.0, 1)}
            for k in PRODUCT_KATEGORI
        ]
        rows.sort(key=lambda r: -r["amount"])
        return rows

    def _beranda_detail(self, date_from, date_to, clean_outlet_ids, finance, fin_prev, summary, sales, ops, prev_from_s, prev_to_s):
        d1 = date.fromisoformat(date_from)
        d2 = date.fromisoformat(date_to)

        # --- 5 KPI utama (kanonik MIS) ---
        income = finance["income_total"] or 0.0
        hpp = finance["hpp_total"] or 0.0
        expense_total = finance["expense_total"] or 0.0
        gross = income - hpp
        opex = expense_total - hpp
        net = finance["net_profit"] or 0.0
        margin = (net / income * 100.0) if income else 0.0

        prev_income = fin_prev["income_total"] or 0.0
        prev_hpp = fin_prev["hpp_total"] or 0.0
        prev_gross = prev_income - prev_hpp
        prev_opex = (fin_prev["expense_total"] or 0.0) - prev_hpp
        prev_net = fin_prev["net_profit"] or 0.0
        prev_margin = (prev_net / prev_income * 100.0) if prev_income else 0.0

        def _pct(cur, prev):
            if prev is None or prev == 0:
                return None
            try:
                return round((cur - prev) / abs(prev) * 100.0, 1)
            except Exception:
                return None

        kpi = {
            "net_revenue": income,
            "hpp_total": hpp,
            "gross_profit": gross,
            "opex": opex,
            "net_profit": net,
            "margin_pct": margin,
        }
        vs = {
            "net_revenue": _pct(income, prev_income),
            "hpp_total": _pct(hpp, prev_hpp),
            "gross_profit": _pct(gross, prev_gross),
            "opex": _pct(opex, prev_opex),
            "net_profit": _pct(net, prev_net),
            "margin_pct": _pct(margin, prev_margin),
        }

        # --- Tren Kinerja harian (pendapatan vs laba) ---
        income_by_day = self._income_by_day(date_from, date_to)
        net_by_day = self._net_income_by_day(date_from, date_to)
        tren = []
        cur = d1
        while cur <= d2:
            key = cur.isoformat()
            tren.append({
                "date": key,
                "pendapatan": income_by_day.get(key, 0.0),
                "laba": net_by_day.get(key, 0.0),
            })
            cur += timedelta(days=1)

        # --- Analisis Channel (legacy — dipakai Tab Penjualan & fallback donut) ---
        # per_outlet dihapus dari payload Beranda — detail outlet tetap
        # tersedia via summary.outlets / sales.
        per_channel = sales.get("channels") or []

        # --- Analisis Kategori Produk (donut Beranda) ---
        # OVERHAUL 15 Sep K3b-rev: donut Beranda = 5 kategori produk
        # (Ayam Geprek / Paket Hemat / Snack & Tambahan / Minuman / Lainnya)
        # via data/category_map.json — sesuai referensi ChatGPT PSAK.
        kategori_produk = self._kategori_produk_detail(date_from, date_to, clean_outlet_ids)

        # --- Kas / Bank / Settlement ---
        cash_positions = finance.get("cash_positions") or []
        kas_bal = sum(p["balance"] for p in cash_positions if p.get("kind") == "kas")
        bank_bal = sum(p["balance"] for p in cash_positions if p.get("kind") != "kas")
        # Outstanding 1103.06 (POS) — saldo per date_to (posted)
        settlement_pending = self._outstanding_balance(date_to)
        # Piutang open total (korporat)
        receivables_total = (finance.get("receivables") or {}).get("total", 0.0)

        # --- Arus Kas PSAK2 (Operasi / Investasi / Pendanaan) — estimasi ---
        # Operasi ≈ laba + penyusutan (non-kas) ; Investasi ≈ -Δ aset tetap ; Pendanaan = plug ke Δ kas
        dep_month = finance.get("depreciation_total") or 0.0
        operasi = net + dep_month
        # Δ aset tetap bulan berjalan — pakai total_gross vs prev month
        try:
            gross_now = (ops.get("assets") or {}).get("total_gross", 0.0)
            # hitung gross prev via snapshot cepat (Aml balance <= prev_to)
            Account = self.env["account.account"].with_context(active_test=False)
            Aml = self.env["account.move.line"]
            fa = Account.search([("account_type", "=", "asset_fixed")])
            prev_gross_accum = 0.0
            for acc, debit, credit in Aml._read_group(
                    [("account_id", "in", fa.ids), ("parent_state", "=", "posted"), ("date", "<=", prev_to_s)],
                    ["account_id"], ["debit:sum", "credit:sum"]):
                bal = (debit or 0.0) - (credit or 0.0)
                if "akumulasi" not in acc.name.lower() and bal > 0.01:
                    prev_gross_accum += bal
            investasi = -(gross_now - prev_gross_accum)  # negatif = cash out
        except Exception:
            investasi = 0.0
        # Δ kas = kas+bank sekarang - kas+bank periode lalu
        try:
            tot_cash_now = self._cash_total_at(date_to)
            tot_cash_prev = self._cash_total_at(prev_to_s)
            delta_cash = tot_cash_now - tot_cash_prev
            pendanaan = delta_cash - operasi - investasi
        except Exception:
            tot_cash_now = kas_bal + bank_bal
            delta_cash = finance.get("cashflow", {}).get("net", 0.0)
            pendanaan = 0.0
            tot_cash_prev = tot_cash_now - delta_cash
        arus_kas_psak = {
            "operasi": operasi,
            "investasi": investasi,
            "pendanaan": pendanaan,
            "net": operasi + investasi + pendanaan,
            "delta_cash": delta_cash,
            "cash_now": tot_cash_now,
            "cash_prev": tot_cash_prev,
        }

        # --- Snapshot Neraca ---
        bal = finance.get("balance") or {}
        snapshot_neraca = {
            "aset": bal.get("total_assets", 0.0),
            "kewajiban": bal.get("liabilities", 0.0),
            "ekuitas": bal.get("equity", 0.0),
            "laba_ditahan": bal.get("net_income_ytd", 0.0),
            "total_liab_ekuitas": bal.get("total_liab_equity", 0.0),
        }

        # --- Laba Bulanan last 6 ---
        laba_bulanan = self._monthly_net_last_n(date_to, n=6)

        return {
            "kpi": kpi,
            "vs": vs,
            "tren": tren,
            "outlet_channel": {"per_channel": per_channel},
            "kategori_produk": kategori_produk,
            "kas_settlement": {
                "kas": kas_bal,
                "bank": bank_bal,
                "settlement_pending": settlement_pending,
                "receivables": receivables_total,
                "total": kas_bal + bank_bal,
            },
            "arus_kas_psak": arus_kas_psak,
            "snapshot_neraca": snapshot_neraca,
            "laba_bulanan": laba_bulanan,
        }

    def _beranda_fallback(self, finance, fin_prev, summary, sales, ops, date_from, date_to):
        """Fallback minimal jika _beranda_detail gagal — tetap render hero."""
        income = finance.get("income_total", 0.0)
        net = finance.get("net_profit", 0.0)
        return {
            "kpi": {
                "net_revenue": income, "hpp_total": finance.get("hpp_total", 0.0),
                "gross_profit": income - finance.get("hpp_total", 0.0),
                "opex": finance.get("expense_total", 0.0) - finance.get("hpp_total", 0.0),
                "net_profit": net, "margin_pct": (net / income * 100.0) if income else 0.0,
            },
            "vs": {"net_revenue": None, "hpp_total": None, "gross_profit": None, "opex": None, "net_profit": None, "margin_pct": None},
            "tren": [],
            "outlet_channel": {"per_channel": sales.get("channels", [])},
            "kategori_produk": [],
            "kas_settlement": {"kas": 0.0, "bank": 0.0, "settlement_pending": 0.0, "receivables": 0.0, "total": 0.0},
            "arus_kas_psak": {"operasi": net, "investasi": 0.0, "pendanaan": 0.0, "net": net, "delta_cash": 0.0, "cash_now": 0.0, "cash_prev": 0.0},
            "snapshot_neraca": {"aset": 0.0, "kewajiban": 0.0, "ekuitas": 0.0, "laba_ditahan": 0.0, "total_liab_ekuitas": 0.0},
            "laba_bulanan": [],
        }

    def _income_by_day(self, date_from, date_to):
        Account = self.env["account.account"].with_context(active_test=False)
        Aml = self.env["account.move.line"]
        inc_accs = Account.search([("account_type", "in", ["income", "income_other"])])
        by_day = defaultdict(float)
        def _k(dt): return dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]
        for dt, debit, credit in Aml._read_group(
                [("date", ">=", date_from), ("date", "<=", date_to), ("parent_state", "=", "posted"),
                 ("account_id", "in", inc_accs.ids)],
                ["date:day"], ["debit:sum", "credit:sum"]):
            if dt:
                by_day[_k(dt)] += (credit or 0.0) - (debit or 0.0)
        return by_day

    def _outstanding_balance(self, date_to):
        try:
            Account = self.env["account.account"].with_context(active_test=False)
            acc = Account.search([("code", "=", "1103.06")], limit=1)
            if not acc:
                return 0.0
            Aml = self.env["account.move.line"]
            rows = Aml._read_group(
                [("account_id", "=", acc.id), ("parent_state", "=", "posted"), ("date", "<=", date_to)],
                [], ["debit:sum", "credit:sum"])
            if not rows:
                return 0.0
            return (rows[0][0] or 0.0) - (rows[0][1] or 0.0)
        except Exception:
            return 0.0

    def _cash_total_at(self, date_to):
        Account = self.env["account.account"].with_context(active_test=False)
        cash_accs = Account.search([("account_type", "=", "asset_cash")])
        total = 0.0
        for acc, debit, credit in self.env["account.move.line"]._read_group(
                [("account_id", "in", cash_accs.ids), ("parent_state", "=", "posted"), ("date", "<=", date_to)],
                ["account_id"], ["debit:sum", "credit:sum"]):
            total += (debit or 0.0) - (credit or 0.0)
        return total

    def _monthly_net_last_n(self, date_to_str, n=6):
        """n bulan terakhir (bulan `date_to_str` = bulan terakhir).

        Tiap bulan mengembalikan: month, label, income, expense, value(=laba
        bersih), hpp, operational, commission, depreciation, gross_profit,
        margin_pct.

        Klasifikasi beban memakai SATU _read_group per bulan (group by akun)
        lalu dibagi ke bucket EKSKLUSIF dengan presedensi sama seperti
        _finance_detail, sehingga HPP + operational + commission +
        depreciation == expense (tabel Laba Rugi bisa di-foot tanpa double
        count):
            account_type == 'expense_direct_cost' → hpp
            nama ~ 'penyusutan'                   → depreciation
            nama ~ 'komisi'                       → commission
            sisanya                               → operational
        Catatan: bucket eksklusif ini menutup celah double count yang ada di
        MIS (row HPP & row Beban Penyusutan dihitung independen).
        """
        import calendar
        d_to = date.fromisoformat(date_to_str)
        # kumpulkan bulan mundur n-1 .. 0
        months = []
        y, m = d_to.year, d_to.month
        for i in range(n-1, -1, -1):
            mm = m - i
            yy = y
            while mm <= 0:
                mm += 12; yy -= 1
            months.append((yy, mm))
        # agregasi GL per bulan (cepat) via _read_group per bulan
        Account = self.env["account.account"].with_context(active_test=False)
        Aml = self.env["account.move.line"]
        inc_accs = Account.search([("account_type", "in", ["income", "income_other"])])
        exp_accs = Account.search([("account_type", "in", self.EXPENSE_TYPES)])
        out = []
        for yy, mm in months:
            last_day = calendar.monthrange(yy, mm)[1]
            d_from = date(yy, mm, 1).isoformat()
            d_to_m = date(yy, mm, last_day).isoformat()
            # FIX BUG_TRIAL_ERROR_2026-09-14: groupby=[] + 2 aggregasi → tuple
            # 2-elemen (debit, credit), BUKAN 3 (account, debit, credit).
            inc = 0.0
            for debit, credit in Aml._read_group(
                    [("date", ">=", d_from), ("date", "<=", d_to_m), ("parent_state", "=", "posted"),
                     ("account_id", "in", inc_accs.ids)], [], ["debit:sum", "credit:sum"]):
                inc += (credit or 0.0) - (debit or 0.0)
            # Beban: group by akun → total + bucket kategori dalam satu query.
            exp = hpp = dep = commission = 0.0
            for acc, debit, credit in Aml._read_group(
                    [("date", ">=", d_from), ("date", "<=", d_to_m), ("parent_state", "=", "posted"),
                     ("account_id", "in", exp_accs.ids)], ["account_id"], ["debit:sum", "credit:sum"]):
                amt = (debit or 0.0) - (credit or 0.0)
                exp += amt
                name_l = (acc.name or "").lower()
                if acc.account_type == "expense_direct_cost":
                    hpp += amt
                elif "penyusutan" in name_l:
                    dep += amt
                elif "komisi" in name_l:
                    commission += amt
            net = inc - exp
            id_months = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
            out.append({
                "month": f"{yy:04d}-{mm:02d}",
                "label": f"{id_months[mm]} {yy}",
                "value": net,
                "income": inc,
                "expense": exp,
                # Rincian komponen biaya per bulan (F5) — dipakai kolom
                # Tabel Laba Rugi Bulanan di dashboard.
                "hpp": hpp,
                "depreciation": dep,
                "commission": commission,
                "operational": exp - hpp - dep - commission,
                "gross_profit": inc - hpp,
                "margin_pct": (net / inc * 100) if inc else 0.0,
            })
        return out

    # ------------------------------------------------------------------
    def _next_day(self, date_str):
        return (date.fromisoformat(date_str) + timedelta(days=1)).isoformat()
