#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit LIVE modul Penagihan (Invoicing / account.move) lewat jalur RPC yang
sama dengan webclient Odoo (login sesi -> /web/dataset/call_kw). Read-only.

Yang diperiksa:
  1. Modul & route GUI Invoicing hidup.
  2. Menu/action seputar penagihan (Invoice, Piutang, Partner Statement...).
  3. Data faktur: total, posted/draft, piutang beredar (residual), overdue.
  4. Laporan penagihan bawaan dashboard (aged_partner, open_items, trial_balance).
  5. Cross-check MIS Cash Flow & Laba Rugi (register terpasang, tanpa sel error).

Jalankan:  python3 scripts/audit_penagihan_gui.py
"""
import json
import os
import sys
from datetime import date

import requests

URL = os.environ.get("ODOO_URL", "http://localhost:8069").rstrip("/")
DB = os.environ.get("ODOO_DB", "Test1")
LOGIN = os.environ.get("ODOO_LOGIN", "Arhamkamal98@gmail.com")
PASSWORD = os.environ.get("ODOO_PASSWORD", "")  # wajib via env, jangan hardcode

s = requests.Session()


def rpc(model, method, args=None, kwargs=None):
    r = s.post(URL + "/web/dataset/call_kw", json={
        "jsonrpc": "2.0", "method": "call",
        "params": {"model": model, "method": method,
                   "args": args or [], "kwargs": kwargs or {}}}, timeout=600).json()
    if "error" in r:
        raise RuntimeError(json.dumps(r["error"], ensure_ascii=False)[:800])
    return r.get("result")


auth = s.post(URL + "/web/session/authenticate", json={
    "jsonrpc": "2.0", "method": "call",
    "params": {"db": DB, "login": LOGIN, "password": PASSWORD}}, timeout=60).json()
if "error" in auth:
    print("LOGIN GAGAL:", json.dumps(auth["error"], ensure_ascii=False)[:300]); sys.exit(1)
res = auth["result"]
uid = res["uid"]
company = res.get("user_companies") or {}
print("Login        : %s (uid %s, DB %s)" % (res["name"], uid, DB))

ver = s.post(URL + "/web/webclient/version_info",
             json={"jsonrpc": "2.0", "method": "call", "params": {}}, timeout=60).json()
print("Versi Odoo   :", ver.get("result", {}).get("server_version"))

# --- 1. modul terpasang ---------------------------------------------------
print("\n=== 1. MODUL TERKAIT PENAGIHAN ===")
mods = rpc("ir.module.module", "search_read",
           [[["name", "in", ["account", "account_financial_report", "partner_statement",
                             "mis_builder", "mis_builder_cash_flow", "report_xlsx",
                             "geprekyukss_dashboard", "account_check_deposit",
                             "account_payment", "mis_builder_inactive_accounts"]]]],
           {"fields": ["name", "shortdesc", "state", "latest_version"], "order": "name"})
for m in mods:
    flag = "OK " if m["state"] == "installed" else "!! "
    print("  %s%-32s %-10s %s" % (flag, m["name"], m["state"], m["shortdesc"] or ""))

# --- 2. route & action GUI penagihan --------------------------------------
print("\n=== 2. ROUTE GUI (webclient) ===")
for path in ["/odoo/invoices", "/odoo/accounting", "/odoo/mis-report-instances"]:
    r = s.get(URL + path, timeout=60, allow_redirects=False)
    print("  GET %-28s -> %s" % (path, r.status_code))

print("\n=== 2b. MENU PENAGIHAN (ir.ui.menu) ===")
menus = rpc("ir.ui.menu", "search_read",
            [[["name", "ilike", "tagih"]]],
            {"fields": ["name", "complete_name", "action"], "limit": 25})
for m in menus:
    print("  [%s] %s  action=%s" % (m["id"], m["complete_name"], m["action"]))
if not menus:
    print("  (tidak ada menu ber-nama 'tagih' — kemungkinan lokalisasi EN)")

print("\n=== 2c. ACTION Invoicing/Piutang (ir.actions.act_window) ===")
acts = rpc("ir.actions.act_window", "search_read",
           [[["res_model", "in", ["account.move", "account.move.line"]]]],
           {"fields": ["name", "path", "res_model", "view_mode", "domain"], "order": "id"})
tag = [a for a in acts if any(k in (a["name"] or "").lower() for k in
       ("invoice", "invoice", "payment", "receivable", "vend", "journal", "bill", "entry", "tagih"))]
for a in (tag or acts)[:30]:
    print("  [%-3s] %-38s model=%-18s path=%s" % (a["id"], (a["name"] or "")[:38],
                                                   a["res_model"], a["path"]))
print("  total action account.move/line:", len(acts))

# --- 3. data faktur --------------------------------------------------------
print("\n=== 3. DATA FAKTUR (account.move) ===")
AM = "account.move"
total = rpc(AM, "search_count", [[["move_type", "in",
         ["out_invoice", "out_refund", "in_invoice", "in_refund"]]]])
posted = rpc(AM, "search_count", [[["move_type", "in",
          ["out_invoice", "out_refund", "in_invoice", "in_refund"]], ["state", "=", "posted"]]])
draft = rpc(AM, "search_count", [[["move_type", "in",
         ["out_invoice", "out_refund", "in_invoice", "in_refund"]], ["state", "=", "draft"]]])
print("  faktur (out/in): total=%s posted=%s draft=%s" % (total, posted, draft))

for mt in ["out_invoice", "out_refund", "in_invoice", "in_refund"]:
    cnt = rpc(AM, "search_count", [[["move_type", "=", mt]]])
    print("    %-12s : %s" % (mt, cnt))

today = str(date.today())
dom_out = [["move_type", "=", "out_invoice"], ["state", "=", "posted"]]
residual = rpc(AM, "read_group", [dom_out,
              ["amount_residual:sum", "amount_total:sum", "amount_residual_signed:sum"], []])
print("  Piutang (out_invoice posted):", residual)
overdue = rpc(AM, "search_count",
              [[["move_type", "=", "out_invoice"], ["state", "=", "posted"],
                ["payment_state", "in", ["not_paid", "partial", "in_payment"]],
                ["invoice_date_due", "<", today]]])
print("  Faktur keluaran lewat jatuh tempo (belum lunas):", overdue)

# Saldo piutang/utang riil dari akun (AML posted) — inti "penagihan"
print("  Saldo akun (AML posted):")
for acc_type, label in [("asset_receivable", "Piutang Usaha"),
                        ("liability_payable", "Utang Usaha")]:
    grp = rpc("account.move.line", "read_group",
              [[["account_id.account_type", "=", acc_type], ["parent_state", "=", "posted"]],
               ["amount_residual:sum"], []])
    amt = grp[0]["amount_residual"] if grp else 0.0
    nopen = rpc("account.move.line", "search_count",
                [[["account_id.account_type", "=", acc_type], ["parent_state", "=", "posted"],
                  ["amount_residual", "!=", 0]]])
    print("    %-14s residual=%14.2f  baris terbuka=%s" % (label, amt or 0.0, nopen))

# AP/AR aging — bucket dihitung di Python dari baris terbuka
from datetime import timedelta


def aging(acc_type, label):
    lines = rpc("account.move.line", "search_read",
                [[["account_id.account_type", "=", acc_type],
                  ["parent_state", "=", "posted"], ["amount_residual", "!=", 0]]],
                {"fields": ["date_maturity", "amount_residual"], "limit": 20000})
    buckets = {"belum jatuh tempo": 0.0, "1-30 hari": 0.0, "31-60 hari": 0.0,
               "61-90 hari": 0.0, "> 90 hari": 0.0}
    for ln in lines:
        amt = ln["amount_residual"] or 0.0
        dm = ln["date_maturity"]
        if not dm:
            buckets["belum jatuh tempo"] += amt
            continue
        due = dm if isinstance(dm, date) else date.fromisoformat(str(dm)[:10])
        days = (date.today() - due).days
        if days <= 0:
            buckets["belum jatuh tempo"] += amt
        elif days <= 30:
            buckets["1-30 hari"] += amt
        elif days <= 60:
            buckets["31-60 hari"] += amt
        elif days <= 90:
            buckets["61-90 hari"] += amt
        else:
            buckets["> 90 hari"] += amt
    print("    %s (%d baris terbuka):" % (label, len(lines)))
    for k, v in buckets.items():
        print("      %-16s %16.2f" % (k, v))


aging("asset_receivable", "Piutang Usaha")
aging("liability_payable", "Utang Usaha")

sample = rpc(AM, "search_read",
             [[["move_type", "in", ["out_invoice", "in_invoice"]], ["state", "=", "posted"]]],
             {"fields": ["name", "partner_id", "invoice_date", "invoice_date_due",
                         "amount_total", "amount_residual", "payment_state", "state"],
              "order": "invoice_date desc", "limit": 8})
print("  8 faktur terbaru (posted):")
print("    %-16s %-26s %-11s %14s %14s %-10s" % ("no", "partner", "tgl", "total", "residual", "bayar"))
for m in sample:
    print("    %-16s %-26s %-11s %14s %14s %-10s" % (
        (m["name"] or "")[:16], ((m["partner_id"] or [0, ""])[1])[:26],
        m["invoice_date"] or "-", "%.0f" % (m["amount_total"] or 0),
        "%.0f" % (m["amount_residual"] or 0), m["payment_state"] or "-"))

# --- 4. laporan penagihan dashboard ---------------------------------------
print("\n=== 4. LAPORAN PENAGIHAN (dashboard report_actions) ===")
params = {"date_from": "2026-01-01", "date_to": "2026-08-31"}
for key in ["aged_partner", "open_items", "trial_balance"]:
    try:
        rep = rpc("geprekyukss.dashboard.report.actions", "get_report_data",
                  [key, params])
        rows = rep.get("rows") or []
        cols = [c.get("key") for c in (rep.get("columns") or [])]
        print("  %-14s kind=%-7s rows=%-6s cols=%s" % (
            key, rep.get("kind"), len(rows), ",".join(cols)[:80]))
        if key == "aged_partner":
            for r in rows[:6]:
                print("      ", json.dumps(r, ensure_ascii=False)[:120])
    except Exception as e:  # noqa: BLE001
        print("  %-14s !! ERROR %s" % (key, str(e)[:200]))

# --- 5. MIS Cash Flow / Laba Rugi -----------------------------------------
print("\n=== 5. MIS REPORT (compute seperti widget) ===")
insts = rpc("mis.report.instance", "search_read", [[]],
            {"fields": ["name"], "order": "id"})
for i in insts:
    try:
        data = rpc("mis.report.instance", "compute", [[i["id"]]], {"context": {}})
    except Exception as e:  # noqa: BLE001
        print("  [%s] %-24s !! ERROR %s" % (i["id"], i["name"], str(e)[:120]))
        continue
    h1 = [c["label"] for c in data["header"][1]["cols"]]
    body = data["body"]
    err = 0
    for row in body:
        for c in row["cells"]:
            vr = c.get("val_r")
            if c.get("cell_id") is None and vr is None:
                continue
            if c.get("val") is None and vr not in (None, "", False):
                err += 1
    print("  [%s] %-24s kolom=%-2s baris=%-3s sel_error=%s" % (
        i["id"], i["name"][:24], len(h1), len(body), err))
    if "cash" in i["name"].lower() or "arus" in i["name"].lower():
        for row in body:
            vals = " ".join(str(c.get("val_r")) for c in row["cells"])
            print("       %-26s %s" % (row["label"][:26], vals))

print("\nSELESAI.")
