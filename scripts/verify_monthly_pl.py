# -*- coding: utf-8 -*-
"""
Verifikasi rincian bulanan Tabel Laba Rugi (F5).

Jalankan di dalam Odoo shell (READ-ONLY — hanya get_dashboard_data):

    docker compose run --rm -T odoo odoo shell -d <NAMA_DB> --no-http \
        < scripts/verify_monthly_pl.py

Yang diperiksa:
 1. Bucket biaya eksklusif → hpp + operational + commission + depreciation
    == expense (per bulan, toleransi 1 rupiah karena pembulatan float).
 2. Bulan terakhir (= periode dashboard) selaras dengan headline kanonik
    di payload finance: income, expense, net_profit, hpp, penyusutan,
    komisi platform.
 3. 6 bulan terakhir berurutan naik & label unik.
"""
TEST_FROM, TEST_TO = "2026-08-01", "2026-08-31"
TOL = 1.0

data_model = env["geprekyukss.dashboard.data"]  # noqa: F821 (odoo shell)
res = data_model.get_dashboard_data(TEST_FROM, TEST_TO, [])
rows = (res.get("beranda") or {}).get("laba_bulanan") or []
fin = res.get("finance") or {}

failures = []


def check(label, got, want):
    ok = abs(got - want) <= TOL
    print(f"  {'OK  ' if ok else 'FAIL'} {label}: {got:,.2f} vs {want:,.2f}")
    if not ok:
        failures.append(label)


print(f"\n=== 1. Bucket biaya eksklusif ({len(rows)} bulan) ===")
print(f"{'bulan':9} {'revenue':>14} {'hpp':>13} {'ops':>13} {'komisi':>11} "
      f"{'penyus':>11} {'expense':>14} {'net':>14}  foot")
if not rows:
    failures.append("laba_bulanan kosong — tidak ada bulan untuk diverifikasi")
for r in rows:
    total = r["hpp"] + r["operational"] + r["commission"] + r["depreciation"]
    diff = abs(total - r["expense"])
    if diff > TOL:
        failures.append(f"bucket {r['label']} tidak foot (selisih {diff:,.2f})")
    print(f"{r['label']:9} {r['income']:>14,.0f} {r['hpp']:>13,.0f} "
          f"{r['operational']:>13,.0f} {r['commission']:>11,.0f} "
          f"{r['depreciation']:>11,.0f} {r['expense']:>14,.0f} "
          f"{r['value']:>14,.0f}  {'ok' if diff <= TOL else 'SELISIH %.2f' % diff}")

if rows:
    print(f"\n=== 2. Bulan terakhir ({rows[-1]['label']}) vs headline kanonik finance ===")
    last = rows[-1]
    check("income", last["income"], fin.get("income_total", 0.0))
    check("expense", last["expense"], fin.get("expense_total", 0.0))
    check("net_profit", last["value"], fin.get("net_profit", 0.0))
    check("hpp", last["hpp"], fin.get("hpp_total", 0.0))
    check("penyusutan", last["depreciation"], fin.get("depreciation_total", 0.0))
    check("komisi platform", last["commission"], fin.get("platform_commission", 0.0))

    print("\n=== 3. Urutan bulan ===")
    months = [r["month"] for r in rows]
    ascending = months == sorted(months) and len(set(months)) == len(months)
    print(f"  {'OK  ' if ascending else 'FAIL'} {months}")
    if not ascending:
        failures.append("urutan bulan tidak menaik/unik")

    print("\n=== Info: gross profit per bulan (income - hpp) ===")
    for r in rows:
        gp = r.get("gross_profit", 0.0)
        m = r.get("margin_pct", 0.0)
        print(f"  {r['label']:9} gross {gp:>14,.0f}  margin {m:>7.2f}%")

print()
if failures:
    print(f"HASIL: {len(failures)} MASALAH")
    for f in failures:
        print("  -", f)
else:
    print("HASIL: SEMUA CHECK LULUS")
