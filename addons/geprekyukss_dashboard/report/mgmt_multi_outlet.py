# -*- coding: utf-8 -*-
"""Laporan Manajemen Keuangan F&B Multi-Outlet (PDF + XLSX).

Format mengikuti pola laporan manajemen emiten F&B (PSAK): laba rugi per outlet
& konsolidasi, indikator kinerja operasional, PBJT (pajak daerah), rekonsiliasi
penerimaan per metode pembayaran, posisi keuangan, dan arus kas ringkas.

Semua angka diambil dari satu sumber kanonik: model
`geprekyukss.dashboard.data` (baca-saja). Laporan TIDAK memutasi data.

Catatan penyajian (penting, jujur soal keterbatasan data):
- Revenue/sales = nilai POS (`price_subtotal_incl`, sudah termasuk PBJT yang
  tertanam di harga). Beban operasional hanya tersedia di level konsolidasi
  (GL tidak membawa dimensi outlet), sehingga laba per outlet disajikan sebagai
  margin kontribusi (revenue − HPP estimasi), bukan laba bersih outlet.
- PBJT disajikan sebagai memo liabilitas.
"""
import calendar
from datetime import date, datetime

from odoo import api, models

ID_MONTHS = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
ID_MONTHS_SHORT = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                   "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _fnum(v):
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _pct(part, whole):
    whole = _fnum(whole)
    return (_fnum(part) / whole * 100.0) if whole else 0.0


class ReportMgmtMultiOutlet(models.AbstractModel):
    _name = "report.geprekyukss_dashboard.report_mgmt_multi_outlet"
    _description = "Laporan Manajemen Multi-Outlet — sumber nilai (PDF)"

    # ------------------------------------------------------------------
    # Entry point QWeb
    # ------------------------------------------------------------------
    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        return {
            "doc_ids": docids,
            "doc_model": "res.company",
            "v": self.collect_values(data),
            "fmt": self._fmt_money,
            "fmt_signed": lambda x: self._fmt_money(x, signed=True),
            "fmt_pct": self._fmt_pct,
            "fmt_dec": self._fmt_dec,
            "fmt_int": self._fmt_int,
        }

    # ------------------------------------------------------------------
    # Format angka gaya Indonesia (ribuan ".")
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_money(value, signed=False):
        v = _fnum(value)
        negative = v < 0
        s = "{:,.0f}".format(abs(v)).replace(",", ".")
        if negative:
            return "(%s)" % s
        if signed and v > 0:
            return "+%s" % s
        return s

    @staticmethod
    def _fmt_pct(value, dec=1):
        v = _fnum(value)
        s = ("{:,.%df}" % dec).format(v)
        s = s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
        return s + "%"

    @staticmethod
    def _fmt_int(value):
        return "{:,}".format(int(_fnum(value))).replace(",", ".")

    @staticmethod
    def _fmt_dec(value, dec=1):
        v = _fnum(value)
        s = ("{:,.%df}" % dec).format(v)
        return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


    # ------------------------------------------------------------------
    # Pengumpulan & penyusunan nilai (dipakai PDF dan XLSX)
    # ------------------------------------------------------------------
    @api.model
    def collect_values(self, data):
        data = data or {}
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        if not date_from or not date_to:
            today = date.today()
            date_from = date_to = today.isoformat()
        date_from = str(date_from)[:10]
        date_to = str(date_to)[:10]

        Dashboard = self.env["geprekyukss.dashboard.data"]
        cons = Dashboard.get_dashboard_data(date_from, date_to)
        if not isinstance(cons, dict):
            cons = {}
        cons_summary = cons.get("summary") or {}
        cons_finance = cons.get("finance") or {}
        cons_sales = cons.get("sales") or {}
        cons_beranda = cons.get("beranda") or {}
        cons_pbjt = cons.get("pbjt") or {}
        has_data = bool(cons.get("has_data"))

        d1 = date.fromisoformat(date_from)
        d2 = date.fromisoformat(date_to)
        days = (d2 - d1).days + 1

        outlets_meta = Dashboard.list_available_outlets() or []
        outlets_meta = sorted(outlets_meta, key=lambda r: r.get("id") or 0)
        by_id = {o["id"]: o for o in outlets_meta}
        pbjt_by_outlet = {r.get("outlet_id"): r for r in (cons_pbjt.get("per_outlet") or [])}
        sum_outlets = {o["config_id"]: o for o in (cons_summary.get("outlets") or [])}

        outlets = []
        for oid, meta in by_id.items():
            od = Dashboard.get_dashboard_data(date_from, date_to, [oid])
            if not isinstance(od, dict):
                od = {}
            o_sum = od.get("summary") or {}
            contrib = od.get("outlet_contribution") or {}
            pbjt_o = pbjt_by_outlet.get(oid) or {}
            gross = _fnum(o_sum.get("amount_total", 0.0))
            tax = _fnum(pbjt_o.get("real_tax", 0.0))
            netto = _fnum(pbjt_o.get("dpp", gross - tax)) if pbjt_o else gross
            hpp = _fnum(contrib.get("cogs_estimate", 0.0))
            outlet_sum = sum_outlets.get(oid) or {}
            orders = int(outlet_sum.get("order_count", o_sum.get("order_count", 0)) or 0)
            avg_ticket = _fnum(outlet_sum.get("avg_ticket", 0.0))
            per_day = (netto / days) if days else 0.0
            outlets.append({
                "id": oid,
                "name": meta.get("name") or outlet_sum.get("name") or ("Outlet %s" % oid),
                "gross": gross,
                "tax": tax,
                "netto": netto,
                "hpp": hpp,
                "gross_profit": netto - hpp,
                "margin": _pct(netto - hpp, netto),
                "order_count": orders,
                "avg_ticket": avg_ticket,
                "per_day": per_day,
                "per_day_orders": (orders / days) if days else 0.0,
                "food_cost_pct": _pct(hpp, netto),
            })

        sum_of = lambda key: sum(_fnum(o[key]) for o in outlets)

        # --- Konsolidasi (kanonik GL) --------------------------------------
        income = _fnum(cons_finance.get("income_total", 0.0))
        hpp_total = _fnum(cons_finance.get("hpp_total", 0.0))
        gross_profit = income - hpp_total
        dep_total = _fnum(cons_finance.get("depreciation_total", 0.0))
        expense_total = _fnum(cons_finance.get("expense_total", 0.0))
        net_profit = _fnum(cons_finance.get("net_profit", 0.0))

        opex_lines = []
        dep_lines = []
        for e in cons_finance.get("expenses") or []:
            name_l = (e.get("name") or "").lower()
            cat = e.get("category") or ""
            if cat == "hpp" or e.get("type") == "expense_direct_cost":
                continue
            if cat == "depreciation" or "penyusutan" in name_l:
                dep_lines.append(e)
            else:
                opex_lines.append(e)
        opex_lines.sort(key=lambda e: -_fnum(e.get("amount")))
        opex_total = sum(_fnum(e.get("amount")) for e in opex_lines)
        ebitda = gross_profit - opex_total
        ebit = ebitda - dep_total

        # --- Indikator operasional ----------------------------------------
        indicators = []
        for o in outlets:
            indicators.append({
                "name": o["name"],
                "order_count": o["order_count"],
                "avg_ticket": o["avg_ticket"],
                "per_day": o["per_day"],
                "per_day_orders": o["per_day_orders"],
                "food_cost_pct": o["food_cost_pct"],
            })
        indicators_total = {
            "name": "Konsolidasi",
            "order_count": int(cons_summary.get("order_count", 0) or 0),
            "avg_ticket": _fnum(cons_summary.get("avg_ticket", 0.0)),
            "per_day": _fnum(cons_summary.get("amount_total", 0.0)) / days if days else 0.0,
            "per_day_orders": _fnum(cons_summary.get("order_count", 0)) / days if days else 0.0,
            "food_cost_pct": _pct(hpp_total, income),
        }

        # --- PBJT (memo liabilitas) ----------------------------------------
        pbjt_rows = []
        for p in cons_pbjt.get("per_outlet") or []:
            gap = _fnum(p.get("gap"))
            pbjt_rows.append({
                "outlet": p.get("outlet"),
                "daerah": p.get("daerah"),
                "gross": _fnum(p.get("gross")),
                "dpp": _fnum(p.get("dpp")),
                "real_tax": _fnum(p.get("real_tax")),
                "negotiated": _fnum(p.get("negotiated")),
                "gap": gap,
                "gap_class": "neg" if gap > 0 else "pos",
            })
        pbjt = {
            "rows": pbjt_rows,
            "totals": cons_pbjt.get("totals") or {},
            "config_count": cons_pbjt.get("config_count", 0),
        }

        # --- Rekonsiliasi penerimaan per metode pembayaran -----------------
        payments = []
        for p in cons_sales.get("payments") or []:
            payments.append({
                "name": p.get("name") or p.get("group") or "Lainnya",
                "group": p.get("group") or "",
                "amount": _fnum(p.get("amount")),
                "order_count": int(p.get("order_count", 0) or 0),
            })
        payments_total = sum(p["amount"] for p in payments)
        for p in payments:
            p["pct"] = _pct(p["amount"], payments_total)

        # --- Posisi keuangan & arus kas ------------------------------------
        balance = self._balance_sheet(date_to)
        cashflow = cons_beranda.get("arus_kas_psak") or {}

        period_short = "%s %s" % (ID_MONTHS[d2.month], d2.year)
        # --- Indikator vs target manajemen (flag sehat/review) -------------
        def _chk(label, actual, target, threshold):
            delta = actual - target
            return {
                "label": label,
                "actual": actual,
                "target": target,
                "delta": delta,
                "ok": abs(delta) <= threshold,
                "tone": "ok" if abs(delta) <= threshold else "warn",
            }
        checks = [
            _chk("Food cost", _pct(hpp_total, income), 35.0, 4.0),
            _chk("Gross margin", _pct(gross_profit, income), 65.0, 6.0),
            _chk("Net margin", _pct(net_profit, income), 12.0, 6.0),
            _chk("Beban gaji", _pct(sum(_fnum(e.get("amount")) for e in (cons_finance.get("expenses") or []) if e.get("code") == "6101.03"), income), 18.0, 4.0),
        ]
        return {
            "company_name": self.env.company.name or "Perusahaan",
            "address": (self.env.company.partner_id.city or ""),
            "date_from": date_from,
            "date_to": date_to,
            "period_label": period_short,
            "days": days,
            "currency": "IDR",
            "has_data": has_data,
            "generated_at": datetime.now().strftime("%d %B %Y %H:%M"),
            "outlets": outlets,
            # kolom total tabel per-outlet
            "outlet_total": {
                "gross": sum_of("gross"),
                "tax": sum_of("tax"),
                "netto": sum_of("netto"),
                "hpp": sum_of("hpp"),
                "gross_profit": sum_of("gross_profit"),
                "margin": _pct(sum_of("gross_profit"), sum_of("netto")),
                "order_count": sum_of("order_count"),
                "avg_ticket": (sum_of("gross") / sum_of("order_count")) if sum_of("order_count") else 0.0,
                "per_day": sum_of("per_day"),
            },
            # P&L konsolidasi kanonik
            "pl": {
                "income": income,
                "hpp": hpp_total,
                "gross_profit": gross_profit,
                "gross_margin": _pct(gross_profit, income),
                "opex_lines": opex_lines,
                "opex_total": opex_total,
                "ebitda": ebitda,
                "ebitda_margin": _pct(ebitda, income),
                "dep_total": dep_total,
                "dep_lines": dep_lines,
                "ebit": ebit,
                "ebit_margin": _pct(ebit, income),
                "net_profit": net_profit,
                "net_margin": _pct(net_profit, income),
                "net_profit_ytd": _fnum(cons_finance.get("net_profit_ytd", 0.0)),
            },
            "indicators": indicators,
            "indicators_total": indicators_total,
            "pbjt": pbjt,
            "payments": payments,
            "payments_total": payments_total,
            "balance": balance,
            "cashflow": cashflow,
            "summary": {
                "amount_total": _fnum(cons_summary.get("amount_total", 0.0)),
                "order_count": int(cons_summary.get("order_count", 0) or 0),
                "vs": cons_summary.get("vs") or {},
            },
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # Neraca detail per akun (as-of date_to)
    # ------------------------------------------------------------------
    def _balance_sheet(self, date_to):
        Aml = self.env["account.move.line"]
        assets, liabilities, equity = [], [], []
        a_tot = l_tot = eq_tot = 0.0
        for acc, debit, credit in Aml._read_group(
                [("parent_state", "=", "posted"), ("date", "<=", date_to)],
                ["account_id"], ["debit:sum", "credit:sum"]):
            bal = _fnum(debit) - _fnum(credit)
            at = acc.account_type or ""
            row = {"code": acc.code or "", "name": acc.name or "", "amount": 0.0}
            if at.startswith("asset"):
                row["amount"] = bal
                assets.append(row)
                a_tot += bal
            elif at.startswith("liability"):
                row["amount"] = -bal
                liabilities.append(row)
                l_tot += -bal
            elif at.startswith("equity"):
                row["amount"] = -bal
                equity.append(row)
                eq_tot += -bal
        # Laba (rugi) tahun berjalan = −Σ(income+expense) s/d date_to
        earnings = 0.0
        for acc, debit, credit in Aml._read_group(
                [("parent_state", "=", "posted"), ("date", "<=", date_to),
                 ("account_id.account_type", "in", [
                     "income", "income_other", "expense", "expense_direct_cost", "expense_depreciation"])],
                ["account_id"], ["debit:sum", "credit:sum"]):
            earnings -= (_fnum(debit) - _fnum(credit))
        if abs(earnings) >= 0.01:
            equity.append({"code": "", "name": "Laba (Rugi) Tahun Berjalan", "amount": earnings})
            eq_tot += earnings
        assets.sort(key=lambda r: r["code"])
        liabilities.sort(key=lambda r: r["code"])
        equity.sort(key=lambda r: r["code"])
        left = [dict(r) for r in assets]
        left.append({"name": "Total Aset", "amount": a_tot, "bold": True})
        right = [dict(r) for r in liabilities]
        right.append({"name": "Total Liabilitas", "amount": l_tot, "bold": True})
        right += [dict(r) for r in equity]
        right.append({"name": "Total Liabilitas & Ekuitas", "amount": l_tot + eq_tot, "bold": True})
        pairs = []
        for i in range(max(len(left), len(right))):
            lrow = left[i] if i < len(left) else None
            rrow = right[i] if i < len(right) else None
            pairs.append({
                "lname": ((lrow.get("code", "") + " " if lrow and lrow.get("code") else "") + lrow["name"]) if lrow else "",
                "lval": lrow["amount"] if lrow else None,
                "lbold": bool(lrow and lrow.get("bold")),
                "rname": ((rrow.get("code", "") + " " if rrow and rrow.get("code") else "") + rrow["name"]) if rrow else "",
                "rval": rrow["amount"] if rrow else None,
                "rbold": bool(rrow and rrow.get("bold")),
            })
        return {
            "assets": assets, "assets_total": a_tot,
            "liabilities": liabilities, "liabilities_total": l_tot,
            "equity": equity, "equity_total": eq_tot,
            "current_earnings": earnings,
            "liab_equity_total": l_tot + eq_tot,
            "pairs": pairs,
        }


class ReportMgmtMultiOutletXlsx(models.AbstractModel):
    _name = "report.geprekyukss_dashboard.report_mgmt_multi_outlet_xlsx"
    _description = "Laporan Manajemen Multi-Outlet (XLSX)"
    _inherit = "report.report_xlsx.abstract"

    def generate_xlsx_report(self, workbook, data, objs):
        v = self.env["report.geprekyukss_dashboard.report_mgmt_multi_outlet"].collect_values(data)

        fmt_title = workbook.add_format({"bold": True, "font_size": 15, "font_color": "#0b2545"})
        fmt_sub = workbook.add_format({"font_size": 9, "font_color": "#64748b"})
        fmt_section = workbook.add_format({"bold": True, "font_size": 11, "bg_color": "#0b2545",
                                           "font_color": "#ffffff", "border": 1})
        fmt_head = workbook.add_format({"bold": True, "border": 1, "bg_color": "#e2e8f0",
                                        "align": "center", "valign": "vcenter", "text_wrap": True})
        fmt_label = workbook.add_format({"border": 1})
        fmt_label_bold = workbook.add_format({"border": 1, "bold": True})
        fmt_money = workbook.add_format({"border": 1, "num_format": "#,##0"})
        fmt_money_b = workbook.add_format({"border": 1, "num_format": "#,##0", "bold": True})
        fmt_pct = workbook.add_format({"border": 1, "num_format": '0.0"%"'})
        fmt_int = workbook.add_format({"border": 1, "num_format": "#,##0"})

        ws = workbook.add_worksheet("Laba Rugi")
        ws.set_column(0, 0, 42)
        for c in range(1, 6):
            ws.set_column(c, c, 18)
        ws.write(0, 0, v["company_name"], fmt_title)
        ws.write(1, 0, "Laporan Laba Rugi Manajemen per Outlet & Konsolidasi", fmt_sub)
        ws.write(2, 0, "Bulan yang berakhir %s · Disajikan dalam Rupiah" % v["date_to"], fmt_sub)

        r = 4
        heads = ["Keterangan"] + [o["name"] for o in v["outlets"]] + ["Total Outlet"]
        for i, h in enumerate(heads):
            ws.write(r, i, h, fmt_head)
        r += 1
        rows = [
            ("Penjualan bruto (termasuk PBJT)", "gross", "money"),
            ("PBJT (10%, termasuk harga)", "tax", "money"),
            ("Penjualan neto (di luar PBJT)", "netto", "money"),
            ("Harga pokok penjualan (estimasi)", "hpp", "money"),
            ("Margin kontribusi outlet", "gross_profit", "money"),
        ]
        for label, key, kind in rows:
            ws.write(r, 0, label, fmt_label_bold if "Margin" in label else fmt_label)
            for i, o in enumerate(v["outlets"]):
                ws.write_number(r, i + 1, _fnum(o[key]), fmt_money_b if "Margin" in label else fmt_money)
            ws.write_number(r, len(v["outlets"]) + 1, _fnum(v["outlet_total"][key]),
                            fmt_money_b if "Margin" in label else fmt_money)
            r += 1
        ws.write(r, 0, "Margin kontribusi (%)", fmt_label)
        for i, o in enumerate(v["outlets"]):
            ws.write_number(r, i + 1, _fnum(o["margin"]), fmt_pct)
        ws.write_number(r, len(v["outlets"]) + 1, _fnum(v["outlet_total"]["margin"]), fmt_pct)
        r += 2

        # P&L konsolidasi
        r = self._xl_section(ws, r, "Laba Rugi Konsolidasi (buku besar)", fmt_section)
        pl = v["pl"]
        for label, val, bold in [
            ("Penjualan neto", pl["income"], False),
            ("Harga pokok penjualan", -pl["hpp"], False),
            ("Laba bruto", pl["gross_profit"], True),
        ]:
            ws.write(r, 0, label, fmt_label_bold if bold else fmt_label)
            ws.write_number(r, 1, val, fmt_money_b if bold else fmt_money)
            r += 1
        for e in pl["opex_lines"]:
            ws.write(r, 0, "   %s" % e.get("name"), fmt_label)
            ws.write_number(r, 1, -_fnum(e.get("amount")), fmt_money)
            r += 1
        for label, val, bold in [
            ("Total beban operasional", -pl["opex_total"], True),
            ("EBITDA", pl["ebitda"], True),
            ("Penyusutan", -pl["dep_total"], False),
            ("Laba usaha (EBIT)", pl["ebit"], True),
            ("LABA BERSIH PERIODE BERJALAN", pl["net_profit"], True),
        ]:
            ws.write(r, 0, label, fmt_label_bold if bold else fmt_label)
            ws.write_number(r, 1, val, fmt_money_b if bold else fmt_money)
            r += 1
        ws.write(r, 0, "Margin bersih (%)", fmt_label)
        ws.write_number(r, 1, pl["net_margin"], fmt_pct)
        r += 2

        # Indikator operasional
        r = self._xl_section(ws, r, "Indikator Kinerja Operasional", fmt_section)
        for i, h in enumerate(["Indikator"] + [o["name"] for o in v["outlets"]] + ["Konsolidasi"]):
            ws.write(r, i, h, fmt_head)
        r += 1
        it = v["indicators_total"]
        ind_rows = [
            ("Jumlah transaksi (struk)", "order_count", fmt_int),
            ("Rata-rata nilai per struk", "avg_ticket", fmt_money),
            ("Penjualan neto per hari", "per_day", fmt_money),
            ("Food cost aktual (%)", "food_cost_pct", fmt_pct),
        ]
        for label, key, fmt in ind_rows:
            ws.write(r, 0, label, fmt_label)
            for i, o in enumerate(v["indicators"]):
                ws.write_number(r, i + 1, _fnum(o[key]), fmt)
            ws.write_number(r, len(v["indicators"]) + 1, _fnum(it[key]), fmt)
            r += 1
        r += 1

        # PBJT
        r = self._xl_section(ws, r, "Pajak Daerah PBJT (memo liabilitas)", fmt_section)
        for i, h in enumerate(["Outlet", "Penjualan bruto", "DPP", "PBJT riil", "Dibayar", "Selisih"]):
            ws.write(r, i, h, fmt_head)
        r += 1
        for o in v["pbjt"]["rows"]:
            ws.write(r, 0, o.get("outlet"), fmt_label)
            for i, k in enumerate(["gross", "dpp", "real_tax", "negotiated", "gap"]):
                ws.write_number(r, i + 1, _fnum(o.get(k)), fmt_money)
            r += 1
        t = v["pbjt"]["totals"]
        ws.write(r, 0, "Total", fmt_label_bold)
        for i, k in enumerate(["gross", "dpp", "real_tax", "negotiated", "gap"]):
            ws.write_number(r, i + 1, _fnum(t.get(k)), fmt_money_b)
        r += 2

        # Pembayaran
        r = self._xl_section(ws, r, "Rekonsiliasi Penerimaan per Metode Pembayaran", fmt_section)
        for i, h in enumerate(["Metode", "Jumlah transaksi", "Nilai"]):
            ws.write(r, i, h, fmt_head)
        r += 1
        for p in v["payments"]:
            ws.write(r, 0, p["name"], fmt_label)
            ws.write_number(r, 1, p["order_count"], fmt_int)
            ws.write_number(r, 2, p["amount"], fmt_money)
            r += 1
        ws.write(r, 0, "Total POS", fmt_label_bold)
        ws.write_number(r, 2, v["payments_total"], fmt_money_b)
        r += 2

        # Neraca
        r = self._xl_section(ws, r, "Posisi Keuangan per %s" % v["date_to"], fmt_section)
        for i, h in enumerate(["Aset", "Jumlah", "Liabilitas & Ekuitas", "Jumlah"]):
            ws.write(r, i, h, fmt_head)
        r += 1
        b = v["balance"]
        left = [{"name": a["code"] + " " + a["name"], "amount": a["amount"]} for a in b["assets"]]
        left.append({"name": "Total Aset", "amount": b["assets_total"], "bold": True})
        right = [{"name": x["code"] + " " + x["name"], "amount": x["amount"]}
                 for x in b["liabilities"]]
        right.append({"name": "Total Liabilitas", "amount": b["liabilities_total"], "bold": True})
        right += [{"name": x["code"] + " " + x["name"], "amount": x["amount"]} for x in b["equity"]]
        right.append({"name": "Total Liabilitas & Ekuitas", "amount": b["liab_equity_total"], "bold": True})
        n = max(len(left), len(right))
        for i in range(n):
            if i < len(left):
                li = left[i]
                ws.write(r + i, 0, li["name"], fmt_label_bold if li.get("bold") else fmt_label)
                ws.write_number(r + i, 1, li["amount"], fmt_money_b if li.get("bold") else fmt_money)
            if i < len(right):
                ri = right[i]
                ws.write(r + i, 2, ri["name"], fmt_label_bold if ri.get("bold") else fmt_label)
                ws.write_number(r + i, 3, ri["amount"], fmt_money_b if ri.get("bold") else fmt_money)
        r += n + 2

        # Arus kas
        r = self._xl_section(ws, r, "Arus Kas Ringkas (metode tak langsung)", fmt_section)
        cf = v["cashflow"]
        for label, key in [("Arus kas dari operasi", "operasi"),
                           ("Arus kas dari investasi", "investasi"),
                           ("Arus kas dari pendanaan", "pendanaan"),
                           ("Kenaikan (penurunan) neto kas", "delta_cash")]:
            ws.write(r, 0, label, fmt_label)
            ws.write_number(r, 1, _fnum(cf.get(key)), fmt_money)
            r += 1
        ws.write(r, 0, "Kas akhir periode", fmt_label_bold)
        ws.write_number(r, 1, _fnum(cf.get("cash_now")), fmt_money_b)
        r += 2
        ws.write(r, 0, "Laporan ini dihasilkan otomatis dari Odoo ERP. Angka per outlet "
                       "adalah margin kontribusi (HPP estimasi); beban operasional hanya konsolidasi.",
                 fmt_sub)

    @staticmethod
    def _xl_section(ws, r, title, fmt_section):
        ws.merge_range(r, 0, r, 5, title, fmt_section)
        return r + 1
