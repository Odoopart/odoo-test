#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kembalikan dashboard NATIVE Odoo (O-Spreadsheet) id 2, 3, 5 ke BAWAAN Odoo.

Latar: `scripts/perbaikan_dashboard_pos.py` (22 Sep 2026) menimpa isi ketiga dashboard
itu dengan elemen buatan sendiri (15/15/8 pivot, 6/6/4 chart, kartu KPI, tangga laba,
catatan opex, judul & nama diubah jadi "Penjualan (POS)" / "Penjualan Restoran (POS)" /
"Operasional POS"), plus `sample_dashboard_file_path` dikosongkan.

Skrip ini mengembalikannya ke definisi yang DIKIRIM MODUL Odoo, dibaca langsung dari
`<module>/data/dashboards.xml` — bukan nilai yang ditulis ulang di sini:

  * name, spreadsheet_binary_data (file .json bawaan), sample_dashboard_file_path,
    dashboard_group_id, sequence, is_published   -> persis nilai XML bawaan;

  * main_data_model_ids -> default modul, DENGAN satu penyesuaian yang dijelaskan di
    bawah (tidak mengubah tampilan sama sekali, hanya menentukan asal angka).

CATATAN soal DATA (jangan dilewatkan):
  Odoo menyajikan file SAMPLE (angka demo) bila `_dashboard_is_empty()` True, yaitu bila
  SALAH SATU model di `main_data_model_ids` kosong
  (spreadsheet_dashboard/controllers/dashboards_controllers.py:21).
  Default id 2 & 3 memakai `sale.order`, yang di DB ini 0 baris -> dashboard bawaan akan
  menampilkan ANGKA DEMO, bukan data nyata.
  Padahal pivot bawaan id 2 & 3 membaca `sale.report` (133.512 baris; isi nyata POS:
  Jun 127.607.737 / Jul 407.930.687 / Agu 439.318.723 — sama dengan Buku Besar).
  Jadi aturannya: pakai model default bila berisi data; kalau kosong, pakai model yang
  benar-benar dipakai pivot dashboard itu dan berisi data. id 5 defaultnya sudah
  `report.pos.order` + `pos.order` (keduanya berisi) -> tetap persis default.

  Efeknya: UI/layout 100% bawaan Odoo, angkanya dari data asli (sale.report & POS),
  tanpa angka demo.

Aman & idempoten:
  - SEBELUM menulis, isi ketiga dashboard sekarang di-backup ke
    `backups/native_dashboard_revert_<timestamp>/dashboard_<id>.json`
  - skrip boleh dijalankan berulang; hasilnya sama.
  - catatan: record dashboard TIDAK `noupdate`, jadi `-u spreadsheet_dashboard_sale`
    juga akan mengembalikan nilainya (dan sekaligus membatalkan pilihan
    `main_data_model_ids` di atas) — jalankan skrip ini lagi setelah upgrade modul.

Jalankan:  python3 scripts/kembalikan_dashboard_native.py
"""
import base64
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests

URL = os.environ.get("ODOO_URL", "http://localhost:8069").rstrip("/")
DB = os.environ.get("ODOO_DB", "Test1")
LOGIN = os.environ.get("ODOO_LOGIN", "Arhamkamal98@gmail.com")
PASSWORD = os.environ.get("ODOO_PASSWORD", "Lowongan01")
ODOO_ADDONS = os.environ.get("ODOO_ADDONS", "/usr/lib/python3/dist-packages/odoo/addons")
BACKUP_ROOT = os.environ.get("BACKUP_ROOT", "backups")

# (module, xml_id record dashboard) — id DB-nya dicari lewat ir.model.data, bukan di-hardcode
TARGETS = [
    ("spreadsheet_dashboard_sale", "spreadsheet_dashboard_sales"),        # sekarang id 2
    ("spreadsheet_dashboard_sale", "spreadsheet_dashboard_product"),      # sekarang id 3
    ("spreadsheet_dashboard_pos_hr", "spreadsheet_dashboard_pos"),        # sekarang id 5
]

s = requests.Session()


def rpc(model, method, args=None, kwargs=None):
    r = s.post(URL + "/web/dataset/call_kw", json={
        "jsonrpc": "2.0", "method": "call",
        "params": {"model": model, "method": method,
                   "args": args or [], "kwargs": kwargs or {}}}, timeout=300).json()
    if "error" in r:
        raise RuntimeError(json.dumps(r["error"], ensure_ascii=False)[:700])
    return r.get("result")


auth = s.post(URL + "/web/session/authenticate", json={
    "jsonrpc": "2.0", "method": "call",
    "params": {"db": DB, "login": LOGIN, "password": PASSWORD}}, timeout=60).json()
if "error" in auth:
    print("LOGIN GAGAL"); sys.exit(1)
print("Login:", auth["result"]["name"])


def xmlid_res(module, name, model):
    r = rpc("ir.model.data", "search_read", [[["module", "=", module], ["name", "=", name],
                                              ["model", "=", model]]],
            {"fields": ["res_id"], "limit": 1})
    if not r:
        raise RuntimeError("xml_id %s.%s (%s) tidak ditemukan" % (module, name, model))
    return r[0]["res_id"]


def ref_any(xmlid):
    """ref('modul.nama') -> res_id, tanpa peduli modelnya."""
    module, _, name = xmlid.partition(".")
    r = rpc("ir.model.data", "search_read", [[["module", "=", module], ["name", "=", name]]],
            {"fields": ["res_id", "model"], "limit": 1})
    if not r:
        raise RuntimeError("ref(%s) tidak ditemukan" % xmlid)
    return r[0]["res_id"]


def default_from_module_xml(module, record_id):
    """Baca definisi bawaan record dashboard dari data/dashboards.xml modul Odoo."""
    path = os.path.join(ODOO_ADDONS, module, "data", "dashboards.xml")
    if not os.path.exists(path):
        raise RuntimeError("XML modul tidak ada: %s" % path)
    root = ET.parse(path).getroot()
    rec = None
    for r in root.iter("record"):
        if r.get("id") == record_id and r.get("model") == "spreadsheet.dashboard":
            rec = r
            break
    if rec is None:
        raise RuntimeError("record %s tidak ada di %s" % (record_id, path))

    d = {"xml_path": path}
    for f in rec.findall("field"):
        attr = f.get("name")
        if attr == "name":
            d["name"] = (f.text or "").strip()
        elif attr == "sequence":
            d["sequence"] = int((f.text or "0").strip())
        elif attr == "is_published":
            d["is_published"] = (f.text or "").strip().lower() == "true"
        elif attr == "sample_dashboard_file_path":
            d["sample_dashboard_file_path"] = (f.text or "").strip()
        elif attr == "dashboard_group_id":
            d["dashboard_group_id"] = ref_any(f.get("ref"))
        elif attr == "main_data_model_ids":
            # eval="[(4, ref('sale.model_sale_order')), ...]"
            d["main_models"] = [ref_any(x) for x in re.findall(r"ref\('([^']+)'\)", f.get("eval") or "")]
        elif attr == "spreadsheet_binary_data":
            d["data_file"] = os.path.join(ODOO_ADDONS, f.get("file"))
    for key in ("name", "sample_dashboard_file_path", "data_file", "main_models"):
        if key not in d:
            raise RuntimeError("field %s tidak ada di record %s (%s)" % (key, record_id, path))
    return d


def model_name(mid):
    r = rpc("ir.model", "read", [[mid], ["model"]])
    return r[0]["model"]


def has_rows(mid):
    return rpc(model_name(mid), "search_count", [[]]) > 0


def pivot_models(snap):
    """Model yang benar-benar dipakai dashboard bawaan (pivot + chart)."""
    out = []
    for p in (snap.get("pivots") or {}).values():
        if p.get("model"):
            out.append(p["model"])
    for sh in snap.get("sheets") or []:
        for fg in sh.get("figures") or []:
            m = ((fg.get("data") or {}).get("metaData") or {}).get("resModel")
            if m:
                out.append(m)
    seen = []
    for m in out:
        if m not in seen:
            seen.append(m)
    return seen


def mid_of(model):
    r = rpc("ir.model", "search_read", [[["model", "=", model]]], {"fields": ["id"], "limit": 1})
    return r[0]["id"] if r else None


stamp = time.strftime("%Y%m%d_%H%M%S")
backup_dir = os.path.join(BACKUP_ROOT, "native_dashboard_revert_%s" % stamp)
os.makedirs(backup_dir, exist_ok=True)

for module, record_id in TARGETS:
    did = xmlid_res(module, record_id, "spreadsheet.dashboard")
    d = default_from_module_xml(module, record_id)

    # --- backup kondisi sekarang (sebelum ditimpa) -------------------------
    cur = rpc("spreadsheet.dashboard", "read",
              [[did], ["name", "spreadsheet_data", "sample_dashboard_file_path",
                       "main_data_model_ids"]])[0]
    with open(os.path.join(backup_dir, "dashboard_%d.json" % did), "w", encoding="utf-8") as fh:
        json.dump(cur, fh, ensure_ascii=False, indent=1)

    # --- data bawaan (dari file .json yang dikirim modul) ------------------
    with open(d["data_file"], "rb") as fh:
        raw = fh.read()
    snap = json.loads(raw.decode("utf-8"))

    # --- penjaga "jangan tampilkan angka demo": pilih model berisi data -----
    keep = [m for m in d["main_models"] if has_rows(m)]
    if not keep:
        for m in pivot_models(snap):
            mid = mid_of(m)
            if mid and mid not in d["main_models"] and has_rows(mid):
                keep.append(mid)
    if not keep:
        print("!! %s: tak ada model berisi data, dashboard bisa tampil sample" % d["name"])
    keep = sorted(set(keep))

    vals = {
        "name": d["name"],
        "spreadsheet_binary_data": base64.b64encode(raw).decode("ascii"),
        "sample_dashboard_file_path": d["sample_dashboard_file_path"],
        "dashboard_group_id": d["dashboard_group_id"],
        "sequence": d["sequence"],
        "is_published": d["is_published"],
        "main_data_model_ids": [(6, 0, keep)],
    }
    rpc("spreadsheet.dashboard", "write", [[did], vals])

    # --- verifikasi lewat route yang dipakai frontend ----------------------
    res = s.get(URL + "/spreadsheet/dashboard/data/%d" % did, timeout=180).json()
    sh = res["snapshot"]["sheets"][0]
    figures = sh.get("figures") or []
    print("dash %d (%-22s) -> %-14s pivot=%2d chart=%2d sample=%s models=%s"
          % (did, cur["name"], d["name"], len(res["snapshot"].get("pivots") or {}),
             len(figures), res.get("is_sample", False),
             ",".join(model_name(m) for m in keep)))
    print("        judul sel A1: %s | baris sheet=%s"
          % (str(sh["cells"].get("A1"))[:60], sh.get("rowNumber")))
    if res.get("is_sample"):
        print("        !! masih menyajikan SAMPLE (angka demo) — cek model penjaga")

print("\nBackup kondisi sebelum pemulihan: %s" % backup_dir)
print("SELESAI.")
