#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit PREVIEW MIS Builder lewat GUI (jalur RPC yang sama dengan widget OWL).

Meniru persis apa yang dikerjakan `mis_builder/static/src/components/
mis_report_widget.esm.js` saat halaman /odoo/mis-report-instances diklik
"Preview" pada sebuah instance:

  1. GET  /odoo/mis-report-instances            (route webclient-nya hidup?)
  2. read mis.report.instance  [field widget yang dibaca frontend]
  3. call mis.report.instance.compute(instance_id)   <-- inti preview
  4. periksa matriks hasilnya: kolom, baris, sel error (DataError -> val_r
     berisi nama error, val_c pesannya), baris kosong, dsb.

Jadi kalau di sini "TAMPIL NORMAL", artinya GUI juga normal; kalau ada sel
error, error itu yang muncul di layar kasir/akuntan.

Jalankan:  python3 scripts/audit_mis_preview_gui.py
"""
import json
import os
import re
import sys
import time

import requests

URL = os.environ.get("ODOO_URL", "http://localhost:8069").rstrip("/")
DB = os.environ.get("ODOO_DB", "Test1")
LOGIN = os.environ.get("ODOO_LOGIN", "Arhamkamal98@gmail.com")
PASSWORD = os.environ.get("ODOO_PASSWORD", "Lowongan01")

WIDGET_FIELDS = [
    "name", "report_id", "date_from", "date_to", "date_range_id", "comparison_mode",
    "target_move", "source_aml_model_id", "source_aml_model_name",
    "widget_show_filters", "widget_search_view_id", "widget_show_settings_button",
    "widget_show_pivot_date", "pivot_date", "wide_display_by_default",
    "user_can_read_annotation", "user_can_edit_annotation",
    "display_columns_description", "no_auto_expand_accounts", "temporary",
    "company_id", "landscape_pdf", "sequence",
]
PERIOD_FIELDS = ["name", "mode", "type", "offset", "duration", "date_from", "date_to",
                 "valid", "source", "source_aml_model_id", "is_ytd", "sequence"]

# Nama-nama yang muncul sebagai sel bila ekspresi KPI gagal dievaluasi
# (mis_builder/models/kpimatrix.py:238-240  ->  DataError => val_r = error name)
ERROR_NAMES = {
    "DataError", "NameDataError", "ValueError", "TypeError", "KeyError",
    "ZeroDivisionError", "AttributeError", "IndexError", "AccountingNone",
}

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
print("Login        :", auth["result"]["name"], "(uid %s, DB %s)" % (auth["result"]["uid"], DB))

ver = s.post(URL + "/web/webclient/version_info",
             json={"jsonrpc": "2.0", "method": "call", "params": {}}, timeout=60).json()
print("Versi Odoo   :", ver.get("result", {}).get("server_version"))

# --- 1. route GUI ----------------------------------------------------------
r = s.get(URL + "/odoo/mis-report-instances", timeout=60, allow_redirects=False)
print("Route GUI    : GET /odoo/mis-report-instances -> %s" % r.status_code)

# --- 2. action + daftar instance ------------------------------------------
acts = rpc("ir.actions.act_window", "search_read",
           [[["res_model", "=", "mis.report.instance"]]],
           {"fields": ["name", "path", "domain", "context", "view_mode"], "order": "id"})
print("\n=== ACTION mis.report.instance (%d) ===" % len(acts))
for a in acts:
    print("  id %-4s path=%-34s %s   view_mode=%s"
          % (a["id"], a.get("path"), a["name"], a["view_mode"]))
    if a.get("domain") not in ("[]", None):
        print("        domain=%s" % a["domain"])

ids = rpc("mis.report.instance", "search", [[]], {"order": "id"})
insts = rpc("mis.report.instance", "read", [ids, WIDGET_FIELDS])
print("\n=== INSTANCE (%d) ===" % len(insts))


def fmt(v):
    return "-" if v in (None, False) else str(v)


def num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


for i in insts:
    per = rpc("mis.report.instance.period", "search_read",
              [[["report_instance_id", "=", i["id"]]]],
              {"fields": PERIOD_FIELDS, "order": "sequence,id"})
    print("\n  [%d] %s" % (i["id"], i["name"]))
    print("      laporan=%s | periode laporan: %s -> %s" % (
        i["report_id"][1], fmt(i["date_from"]), fmt(i["date_to"])))
    print("      sumber=%s | target_move=%s | comparison_mode=%s | landscape=%s | temporary=%s"
          % (fmt(i["source_aml_model_name"]), fmt(i["target_move"]),
             i["comparison_mode"], i["landscape_pdf"], i["temporary"]))
    print("      widget: show_filters=%s search_view=%s settings_btn=%s show_pivot=%s "
          "wide=%s annot(read/edit)=%s/%s"
          % (i["widget_show_filters"], fmt(i["widget_search_view_id"]),
             i["widget_show_settings_button"], i["widget_show_pivot_date"],
             i["wide_display_by_default"], i["user_can_read_annotation"],
             i["user_can_edit_annotation"]))
    print("      kolom periode (%d):" % len(per))
    for p in per:
        print("        seq %-4s %-14s mode=%-9s type=%-3s offset=%-6s dur=%-5s %s..%s valid=%s src=%s"
              % (p["sequence"], p["name"], fmt(p["mode"]), fmt(p["type"]), p["offset"],
                 p["duration"], fmt(p["date_from"]), fmt(p["date_to"]), p["valid"],
                 fmt(p["source"])))

# --- 3. compute persis seperti widget -------------------------------------
print("\n\n=== HASIL compute() PER INSTANCE ===")
summary = []
for i in insts:
    ctx = {}
    if i["widget_show_pivot_date"] and i["pivot_date"]:
        ctx["mis_pivot_date"] = i["pivot_date"]
    t0 = time.time()
    try:
        data = rpc("mis.report.instance", "compute", [[i["id"]], ], {"context": ctx})
    except RuntimeError as e:
        print("\n--- [%d] %s -> ERROR COMPUTE ---\n%s" % (i["id"], i["name"], e))
        summary.append((i["id"], i["name"], "ERROR COMPUTE", 0, 0, 0))
        continue
    dt = time.time() - t0

    h0 = [c["label"] for c in data["header"][0]["cols"]]
    h1 = [c["label"] for c in data["header"][1]["cols"]]
    body = data["body"]
    ncol = len(h1)

    err_cells, zero_rows, empty_rows = [], [], []
    for row in body:
        cells = row["cells"]
        vals = []
        for c in cells:
            vr = c.get("val_r")
            v = c.get("val")
            if c.get("cell_id") is None and not vr and v is None:
                continue
            if (v is None) and vr not in (None, "", False):
                if str(vr).strip() in ERROR_NAMES or not re.match(r"^[\d.,\s()\-+%Rp]*$", str(vr)):
                    err_cells.append((row["label"], vr, (c.get("val_c") or "")[:90]))
            vals.append(num(v))
        vals = [v for v in vals if v is not None]
        if not vals:
            empty_rows.append(row["label"])
        elif all(abs(v) < 1e-9 for v in vals):
            zero_rows.append(row["label"])

    print("\n--- [%d] %s   (compute %.2fs) ---" % (i["id"], i["name"], dt))
    print("    kolom level-1 (%d): %s" % (ncol, " | ".join(h1)))
    print("    baris body: %d | notes: %d" % (len(body), len(data.get("notes") or {})))
    if err_cells:
        print("    !! SEL ERROR (%d):" % len(err_cells))
        for lbl, vr, vc in err_cells[:12]:
            print("        %-28s -> %s : %s" % (lbl[:28], vr, vc))
    if empty_rows:
        print("    ?? baris tanpa angka (%d): %s" % (len(empty_rows), "; ".join(empty_rows)[:160]))
    if zero_rows:
        print("    ?? baris semua 0 (%d): %s" % (len(zero_rows), "; ".join(zero_rows)[:160]))

    # matriks ringkas: label + nilai kolom
    print("    %-30s %s" % ("KPI", " ".join("%14s" % c[:14] for c in h1)))
    for row in body[:40]:
        cells = row["cells"]
        cellstr = []
        for k in range(ncol):
            c = cells[k] if k < len(cells) else {}
            txt = c.get("val_r")
            cellstr.append("%14s" % ("" if txt is None else str(txt)[:14]))
        print("    %-30s %s" % (row["label"][:30], " ".join(cellstr)))
    if len(body) > 40:
        print("    ... (%d baris lagi)" % (len(body) - 40))

    verdict = "TAMPIL NORMAL"
    if err_cells:
        verdict = "ADA %d SEL ERROR" % len(err_cells)
    elif not body or not any(0 not in (num(c.get("val")),) for row in body for c in row["cells"]):
        verdict = "SEMUA NOL/KOSONG"
    summary.append((i["id"], i["name"], verdict, len(h2) if False else ncol, len(body),
                    len(err_cells)))

print("\n\n=== RINGKASAN ===")
print("%-4s %-28s %-20s %6s %6s %7s" % ("id", "instance", "verdict", "kolom", "baris", "sel_err"))
for sid, sname, verdict, ncol, nrow, nerr in summary:
    print("%-4s %-28s %-20s %6s %6s %7s" % (sid, sname[:28], verdict, ncol, nrow, nerr))
