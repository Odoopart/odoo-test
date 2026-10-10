#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Setel periode laporan agar portofolio (data Jun 20 - Agu 31 2026) selalu tampil benar.

LATAR (hasil audit 23 Sep 2026):
  Data berhenti 31 Agustus, sedangkan "hari ini" sudah September. Semua laporan
  yang periodenya MENGIKUTI TANGGAL HARI INI jadi kosong. Jadi:
    * dashboard native Odoo 2/3/5 -> filter tanggal `last_90_days`/`last_30_days`
      = ikut hari ini -> September -> hampir kosong;
    * instance MIS (Cash Flow / Laba Rugi / Neraca) -> sebagian kolomnya ditulis
      ulang otomatis oleh `_apply_mis_period()` (report_actions.py) setiap kali
      dashboard/laporan shell dipakai, sehingga label bulan jadi menyesatkan.

YANG DIKERJAKAN SKRIP INI:
  1. Buat `date.range.type` "Bulanan" + `date.range`: Juni/Juli/Agustus 2026 dan
     Jul-Agu 2026 -> supaya periode bisa DIPILIH dari dropdown, bukan diketik manual.
  2. Nyalakan `widget_show_settings_button`, `widget_show_pivot_date`, dan
     `display_columns_description` pada 3 instance MIS:
       - gerigi    : bisa ganti periode tanpa keluar dari halaman preview;
       - base date : kotak "Base date..." di preview = VARIABEL periode laporan.
                     Ubah tanggal itu, SELURUH kolom ikut bergerak (tidak ada
                     tanggal literal di laporan);
       - deskripsi : header kolom menampilkan TANGGAL ASLI hasil hitungan
                     ("from 01/08/2026 to 31/08/2026"), jadi label tidak mungkin
                     menipu walau base date-nya digeser.
  3. Kolom periode ditulis sebagai WINDOW RELATIF terhadap base date — bukan
     tanggal literal. Bentuknya mengikuti bentuk rentangnya: bulan penuh pakai
     satuan BULAN (`type='m'`, panjang 28/30/31 hari menyesuaikan sendiri),
     rentang custom pakai satuan HARI (`type='d'`, persis). Sisi server
     (`report_actions._apply_mis_period`) memakai aturan yang sama saat dashboard
     mengganti bulan. Kolomnya (default periode Agustus 2026):
       - Cash Flow  : 1 kolom "Periode Terpilih" (kolom mingguan +1w..+8w,
                      third/fourth month dibuang - kosong total: 0 forecast line);
       - Laba Rugi  : 2 kolom "Bulan Terpilih" + "YTD" (jumlah kolom DIPERTAHANKAN:
                      dashboard membaca cells[0] dan cells[1]);
       - Neraca     : 2 kolom "Posisi Akhir Periode" + "Posisi Bulan Sebelumnya".
     `date` (Base date) instance = 31 Agu 2026 — satu-satunya angka tetap, dan
     itupun variabel yang bisa digeser dari UI atau dari filter dashboard.
     Bukti bervariasi: geser base date ke 30 Jun / 31 Jul / 31 Des, seluruh
     kolom (termasuk YTD & posisi bulan sebelumnya) bergerak tanpa disetel ulang.
  4. Dashboard native 2/3/5 -> filter tanggal default jadi "All time" (tanpa
     `defaultValue`): tidak pernah kosong, dan pilihan Month / Custom Range tetap
     tersedia di sidebar saat dipakai.

  CATATAN: label sengaja berbasis peran ("Bulan Terpilih"), bukan nama bulan,
  karena tanggal kolom itu ditulis ulang oleh dashboard saat Bapak pindah bulan.
  Tanggal aslinya selalu terlihat lewat fitur deskripsi kolom (poin 2).

Jalankan:  python3 scripts/setup_periode_portofolio.py
"""
import datetime
import json
import os
import sys

import requests

URL = os.environ.get("ODOO_URL", "http://localhost:8069").rstrip("/")
DB = os.environ.get("ODOO_DB", "Test1")
LOGIN = os.environ.get("ODOO_LOGIN", "Arhamkamal98@gmail.com")
PASSWORD = os.environ.get("ODOO_PASSWORD", "Lowongan01")

# (tipe, allow_overlap, nama rentang, dari, sampai)
# `mis.report.instance.period.date_range_type_id` ber-domain allow_overlap=False,
# jadi rentang BULANAN dijadikan satu tipe (tidak tumpang tindih) supaya bisa
# dipilih; rentang gabungan (Jul-Agu) butuh tipe sendiri yang boleh tumpang tindih.
RANGES = [
    ("Bulanan", False, "Juni 2026", "2026-06-01", "2026-06-30"),
    ("Bulanan", False, "Juli 2026", "2026-07-01", "2026-07-31"),
    ("Bulanan", False, "Agustus 2026", "2026-08-01", "2026-08-31"),
    ("Portofolio", True, "Jul-Agu 2026", "2026-07-01", "2026-08-31"),
]
DEFAULT_FROM, DEFAULT_TO = "2026-08-01", "2026-08-31"
BASE_DATE = DEFAULT_TO          # variabel periode: semua kolom relatif ke sini


def window(date_from, date_to, base=BASE_DATE, ytd=False):
    """Rentang tanggal -> window relatif thd base date (offset/duration HARI).

    Dipakai untuk rentang yang TIDAK jatuh di batas bulan (custom), supaya
    rentangnya terwakili persis. PENTING: offset SELALU dihitung dari base
    date, bukan dari `date_to`.

    Rumus yang sama dipakai report_actions._window() di sisi server, jadi
    konfigurasi di sini dan perhitungan shell tidak mungkin berbeda.
    """
    d1 = datetime.date.fromisoformat(date_from[:10])
    d2 = datetime.date.fromisoformat(date_to[:10])
    base_d = datetime.date.fromisoformat(base[:10])
    return {
        "mode": "relative", "type": "d",
        "offset": (d1 - base_d).days,          # relatif ke BASE DATE
        "duration": (d2 - d1).days + 1,
        "is_ytd": ytd,
        "manual_date_from": False, "manual_date_to": False, "date_range_id": False,
    }


def month_window(offset, ytd=False):
    """Kolom = N bulan relatif ke base date (satuan BULAN, bukan hari).

    Ini bentuk yang BENAR untuk bulan penuh: MIS Builder menghitung
    `base.replace(day=1) + N bulan` lalu menutup di hari terakhir bulan itu,
    jadi panjang 28/30/31 hari menyesuaikan sendiri. Satuan hari meleset:
    -30 hari dari 30 Juni = 31 Mei, bukan 1 Juni.
    """
    return {
        "mode": "relative", "type": "m",
        "offset": offset, "duration": 1, "is_ytd": ytd,
        "manual_date_from": False, "manual_date_to": False, "date_range_id": False,
    }


def month_range(base, offset):
    """Tanggal HASIL HITUNGAN MIS Builder untuk month_window() - untuk tampilan."""
    d = datetime.date.fromisoformat(str(base)[:10])
    y, m = d.year, d.month + offset
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    first = datetime.date(y, m, 1)
    last = (first + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    return first.isoformat(), last.isoformat()

INSTANCES = {
    "cash_flow": "mis_builder_cash_flow.mis_instance_cash_flow",
    "pl": "geprekyukss_dashboard.mis_instance_pl",
    "bs": "geprekyukss_dashboard.mis_instance_bs",
}

s = requests.Session()


def rpc(model, method, args=None, kwargs=None):
    r = s.post(URL + "/web/dataset/call_kw", json={
        "jsonrpc": "2.0", "method": "call",
        "params": {"model": model, "method": method,
                   "args": args or [], "kwargs": kwargs or {}}}, timeout=600).json()
    if "error" in r:
        raise RuntimeError(json.dumps(r["error"], ensure_ascii=False)[:700])
    return r.get("result")


auth = s.post(URL + "/web/session/authenticate", json={
    "jsonrpc": "2.0", "method": "call",
    "params": {"db": DB, "login": LOGIN, "password": PASSWORD}}, timeout=60).json()
if "error" in auth:
    print("LOGIN GAGAL"); sys.exit(1)
print("Login:", auth["result"]["name"])


def ref(xmlid):
    mod, nm = xmlid.split(".")
    r = rpc("ir.model.data", "search_read", [[["module", "=", mod], ["name", "=", nm]]],
            {"fields": ["res_id", "model"], "limit": 1})
    if not r:
        raise RuntimeError("xml_id %s tidak ada" % xmlid)
    return r[0]["res_id"]


# --- 1. date.range.type + date.range --------------------------------------
print("\n=== 1. date.range.type / date.range ===")
# URUTAN PENTING: validasi tumpang tindih hanya berjalan pada rentang yang
# tipenya allow_overlap=False. Kalau tipe dikunci lebih dulu, rentang yang
# masih menempel di tipe itu (mis. "Jul-Agu 2026" sisa run sebelumnya) akan
# membuat penulisan rentang lain gagal. Jadi: (A) siapkan tipe -> (B) pindahkan
# rentang ke tipe yang benar -> (C) baru kunci allow_overlap tipe.
type_ids, todo_overlap = {}, {}
for tname, overlap in (("Bulanan", False), ("Portofolio", True)):
    t = rpc("date.range.type", "search_read", [[["name", "=", tname]]],
            {"fields": ["id", "allow_overlap"], "limit": 1})
    if t:
        type_ids[tname] = t[0]["id"]
        todo_overlap[t[0]["id"]] = overlap
        print("   date.range.type %-12s sudah ada (id %s)" % (tname, t[0]["id"]))
    else:
        type_ids[tname] = rpc("date.range.type", "create",
                              [{"name": tname, "allow_overlap": overlap}])
        print("   date.range.type %-12s dibuat (id %s)" % (tname, type_ids[tname]))

# Tipe yang BOLEH tumpang tindih diproses lebih dulu: rentang gabungan (Jul-Agu)
# yang masih menempel di tipe "Bulanan" (allow_overlap=False) akan menggagalkan
# penulisan rentang bulanan mana pun yang bersinggungan dengannya.
for tname, _overlap, name, dfrom, dto in sorted(RANGES, key=lambda r: not r[1]):
    type_id = type_ids[tname]
    found = rpc("date.range", "search_read", [[["name", "=", name]]],
                {"fields": ["id", "type_id"], "limit": 1})
    vals = {"name": name, "type_id": type_id, "date_start": dfrom, "date_end": dto}
    if found:
        rpc("date.range", "write", [[found[0]["id"]], vals])
        print("   date.range %-12s (%-11s) -> %s..%s" % (name, tname, dfrom, dto))
    else:
        rpc("date.range", "create", [vals])
        print("   date.range %-12s (%-11s) -> %s..%s  (baru)" % (name, tname, dfrom, dto))

for tid, overlap in todo_overlap.items():
    rpc("date.range.type", "write", [[tid], {"allow_overlap": overlap}])
    print("   date.range.type id %-3s allow_overlap=%s" % (tid, overlap))

# --- 2. instance MIS: gerigi + deskripsi kolom ----------------------------
print("\n=== 2. Instance MIS: gerigi + base date + deskripsi kolom ===")
inst = {}
for key, xmlid in INSTANCES.items():
    iid = ref(xmlid)
    inst[key] = iid
    rpc("mis.report.instance", "write", [[iid], {
        "widget_show_settings_button": True,
        "widget_show_pivot_date": True,
        "display_columns_description": True,
        "date": BASE_DATE,                 # variabel periode
    }])
    rec = rpc("mis.report.instance", "read", [[iid], [
        "name", "date", "widget_show_settings_button", "widget_show_pivot_date",
        "display_columns_description"]])[0]
    print("   [%s] %-24s base_date=%s settings_btn=%s picker=%s deskripsi=%s"
          % (iid, rec["name"], rec["date"], rec["widget_show_settings_button"],
             rec["widget_show_pivot_date"], rec["display_columns_description"]))

# --- 3. periode tiap instance --------------------------------------------
print("\n=== 3. Kolom periode sebagai window relatif thd base date %s ===" % BASE_DATE)


def ytd_shown(offset=0):
    """Tampilan kolom YTD/posisi: 1 Jan tahun akhir kolom -> akhir bulan kolom."""
    _f, t = month_range(BASE_DATE, offset)
    return "%s-01-01..%s" % (t[:4], t)


def periods(iid):
    return rpc("mis.report.instance.period", "search_read",
               [[["report_instance_id", "=", iid]]],
               {"fields": ["id", "name", "mode", "type", "offset", "duration",
                           "manual_date_from", "manual_date_to", "date_from", "date_to",
                           "sequence", "source", "source_aml_model_id"],
                "order": "sequence,id"})


def set_period(pid, name, vals, shown):
    vals = dict(vals)
    vals["name"] = name
    rpc("mis.report.instance.period", "write", [[pid], vals])
    print("      %-26s relatif: satuan-%-5s offset=%-5s duration=%-3s ytd=%-5s (= %s)"
          % (name, "bulan" if vals["type"] == "m" else "hari",
             vals["offset"], vals["duration"], vals["is_ytd"], shown))


# 3a. Cash Flow: sisakan 1 kolom (kolom mingguan dibuang)
plist = periods(inst["cash_flow"])
if plist:
    print("   [Cash Flow] sumber: %s / %s"
          % (plist[0]["source"],
             plist[0]["source_aml_model_id"] and plist[0]["source_aml_model_id"][1]))
    set_period(plist[0]["id"], "Periode Terpilih", month_window(0),
               "%s..%s" % month_range(BASE_DATE, 0))
drop = [p["id"] for p in plist[1:]]
if drop:
    rpc("mis.report.instance.period", "unlink", [drop])
    print("      %d kolom mingguan/proyeksi dibuang: %s"
          % (len(drop), ", ".join(p["name"] for p in plist[1:])))

# 3b. Laba Rugi: 2 kolom (jumlah kolom WAJIB tetap - dashboard baca cells[0..1])
print("   [Laba Rugi]")
plist = periods(inst["pl"])
if len(plist) >= 2:
    set_period(plist[0]["id"], "Bulan Terpilih", month_window(0),
               "%s..%s" % month_range(BASE_DATE, 0))
    set_period(plist[1]["id"], "YTD", month_window(0, ytd=True), ytd_shown(0))
    if len(plist) > 2:
        rpc("mis.report.instance.period", "unlink", [[p["id"] for p in plist[2:]]])
        print("      %d kolom berlebih dibuang" % (len(plist) - 2))

# 3c. Neraca: 2 kolom
print("   [Neraca]")
plist = periods(inst["bs"])
if len(plist) >= 2:
    set_period(plist[0]["id"], "Posisi Akhir Periode", month_window(0, ytd=True),
               ytd_shown(0))
    set_period(plist[1]["id"], "Posisi Bulan Sebelumnya", month_window(-1, ytd=True),
               ytd_shown(-1))
    if len(plist) > 2:
        rpc("mis.report.instance.period", "unlink", [[p["id"] for p in plist[2:]]])
        print("      %d kolom berlebih dibuang" % (len(plist) - 2))

# --- 4. dashboard native: filter tanggal default -> All time ---------------
print("\n=== 4. Dashboard native 2/3/5: filter tanggal default -> 'All time' ===")
for did in (2, 3, 5):
    rec = rpc("spreadsheet.dashboard", "read", [[did], ["name", "spreadsheet_data"]])[0]
    snap = json.loads(rec["spreadsheet_data"])
    changed = []
    for gf in snap.get("globalFilters") or []:
        if gf.get("type") == "date" and "defaultValue" in gf:
            changed.append(gf.pop("defaultValue"))
    rpc("spreadsheet.dashboard", "write", [[did], {"spreadsheet_data": json.dumps(snap)}])
    print("   dash %d %-16s -> default lama %s dibuang (kini All time)"
          % (did, rec["name"], changed or "belum diset"))

# --- 5. verifikasi: header kolom + tanggal asli ---------------------------
print("\n=== 5. Verifikasi: base date menggeser seluruh kolom (bukti bervariabel) ===")
for key, iid in inst.items():
    data = rpc("mis.report.instance", "compute", [[iid]], {})
    rows = data["body"]
    errs = [r["label"] for r in rows for c in r["cells"]
            if c.get("val") is None and c.get("val_r") and c["val_r"] not in ("", False)
            and not str(c["val_r"]).replace(".", "").replace(",", "").replace("-", "").isdigit()]
    print("   [%s] base=%s" % (key, rpc("mis.report.instance", "read", [[iid], ["date"]])[0]["date"]))
    for c in data["header"][0]["cols"]:
        print("        %-26s | %s" % (c["label"], c["description"] or "-"))
    print("        baris=%d | sel error=%d" % (len(rows), len(errs)))
    if errs:
        print("        !! cek:", errs[:5])

print("\nSELESAI.")
