# Task: Ubah Halaman Awal Odoo agar Menampilkan Modul Terpasang

> **Penting:** gambar referensi mungkin tidak bisa kamu baca (hanya OCR, atau tidak terkirim). Karena itu seluruh tampilan dideskripsikan dalam teks di bawah. **Ikuti teks ini, jangan menebak dari hasil OCR.** Jika gambar terbaca dan berbeda dari teks, ikuti teks lalu laporkan perbedaannya di akhir.

## Konteks
- Versi Odoo: `[ISI, mis. 17.0 / 18.0]`. Jika kosong, deteksi sendiri (`odoo/release.py`).
- Edisi: `[Community / Enterprise]`. Jika kosong, deteksi sendiri (ada `web_enterprise` di addons path = Enterprise).
- Nama modul custom: `home_menu_custom` (boleh diganti).
- Nama perusahaan ("Aetna Inc."), nama user, dan daftar app di bawah hanyalah contoh dari screenshot. Jangan di-hardcode.

## Tujuan
Halaman awal Odoo menampilkan kartu tanggal-jam + pengumuman, lalu grid ikon semua aplikasi (modul terpasang) yang boleh diakses user yang sedang login.

## Langkah 0: investigasi dulu
1. Tentukan versi, edisi, dan addons path.
2. Cari implementasi home/app menu yang aktif sekarang. Enterprise = `HomeMenu` di `web_enterprise`; Community = menu aplikasi di navbar. Cek juga apakah ada modul tema backend pihak ketiga yang menimpanya.
3. Baca source versi yang terpasang untuk API yang akan dipakai (menu service, `webIconData`, registry actions). Jangan mengandalkan ingatan, API berbeda antar versi.
4. Tulis rencana singkat (pendekatan + file yang dibuat/diubah), lalu langsung kerjakan. Jangan berhenti untuk bertanya di tengah jalan: ambil asumsi yang wajar dan catat di laporan akhir.

## Spesifikasi tampilan
Angka di bawah adalah perkiraan (≈) dari screenshot selebar ±1080px. Tidak perlu pixel-perfect; yang penting proporsi dan kesan visualnya sama.

- **Latar:** ungu keabu-abuan ≈ `#8b80b8`. Ada bentuk diagonal lebih gelap (≈ `#7a6fa6`) di area kanan-bawah; tepinya mulai sekitar tengah layar lalu menurun ke pojok kanan-bawah, area di bawah garis lebih gelap. Jika edisi Enterprise, latar bawaan home menu kemungkinan sudah mirip: pakai itu dulu, sesuaikan hanya bila berbeda.
- **Navbar:** kiri = ikon grid + teks "Menu". Kanan, berurutan = ikon chat dengan badge hijau berisi jumlah pesan, ikon jam (aktivitas), ikon bookmark, nama perusahaan aktif, avatar kotak ungu berisi inisial user. Jika sudah ada, jangan diubah.
- **Kartu:** putih, sudut membulat ≈ 6px, shadow halus, tinggi ≈ 60px, lebar ≈ 600px (`max-width: 100%`), rata tengah, ≈ 35px di bawah navbar.
  - Kiri: tanggal kecil (≈ 12px) di atas jam besar tebal (≈ 18px), mis. "Tuesday, June 17, 2025" dan "12:26:49 PM".
  - Kanan: `textarea` mengisi sisa lebar dengan placeholder "Announcement for everyone" (abu muda), lalu tombol "Save" ungu (≈ `#7c6ba6`, teks putih tebal).
- **Grid app:** lebar sama dengan kartu, ≈ 38px di bawah kartu. 6 kolom tetap lebar 60px dengan `justify-content: space-between`, jarak top-ke-top antar baris ≈ 110px. Pakai CSS grid (`repeat(6, 60px)`), bukan flex-wrap, supaya baris terakhir tetap rata kiri mengikuti kolom (tidak ditarik ke tepi).
- **Tile:** persegi 60×60, radius ≈ 8px, border tipis gelap ≈ 1px, shadow halus. Isinya ikon bawaan modul (`webIconData`) yang memenuhi tile. Jangan mengganti ikon.
- **Label:** di bawah tile, putih, ≈ 13px, rata tengah, satu baris. Boleh lebih lebar dari tile (mis. "Point of Sale") tapi tidak boleh menggeser kolom.
- **Responsif:** layar ≤ 768px → grid 3–4 kolom; kartu lebar penuh (jam di atas, textarea di bawahnya).

## Spesifikasi fungsi
1. **Jam:** tanggal dan jam update tiap 1 detik; format dan bahasa mengikuti locale user (di screenshot: en_US, 12 jam AM/PM). Pisahkan komponen jam supaya update tiap detik tidak me-render ulang grid. Bersihkan `setInterval` saat komponen di-unmount.
2. **Grid dinamis:** ambil dari root menu (aplikasi) yang terpasang **dan** boleh diakses user saat ini lewat menu service bawaan web client. Jangan hardcode nama modul. Di screenshot urutannya A→Z berdasarkan nama; jadikan satu konstanta/opsi supaya mudah diganti ke urutan sequence bawaan Odoo.
3. **Klik tile:** membuka aplikasi tersebut (`menuService.selectMenu(app)` atau padanannya di versi terpasang). Jika ikon kosong, pakai fallback bawaan.
4. **Hak akses:** user yang tidak berhak atas suatu app tidak boleh melihatnya. Uji dengan user non-admin (contoh: "Apps" dan "Settings" tidak muncul).
5. **Pengumuman:** teks disimpan di server (field `Text` pada `res.company`, atau model kecil khusus) dan tampil di textarea untuk semua user perusahaan itu. Tombol "Save" mengirim ke server, menampilkan notifikasi sukses, teks tetap tampil. Asumsi default: hanya grup Settings (`base.group_system`) yang boleh mengedit; user lain melihat textarea read-only tanpa tombol Save. Pembatasan ini wajib dicek di server, bukan hanya di UI. Perlakukan sebagai teks biasa (tanpa HTML).
6. **Halaman awal:** halaman ini tampil setelah login dan saat tombol "Menu" di navbar diklik.

## Pendekatan teknis
- Kerjakan **hanya di modul custom**. Jangan edit file core atau enterprise.
- **Enterprise:** `patch()` komponen `HomeMenu` dan extend template-nya dengan `t-inherit` (mode extension). Daftar app dan menu service sudah ada, jadi tinggal tambah kartu dan restyle. Cek nama persis komponen/template di source.
- **Community:** buat komponen OWL baru, daftarkan sebagai client action (`registry.category("actions")` + `ir.actions.client`), jadikan home action (mis. lewat `res.users.action_id`), dan sambungkan tombol "Menu" di navbar ke action itu.
- Daftarkan JS/XML/SCSS di bundle `web.assets_backend` lewat `__manifest__.py`. Tanpa CDN atau library baru. Teks UI pakai `_t()`.
- Ikuti konvensi versi terpasang (OWL, format modul JS, dll.). Kode ringkas dan mudah dibaca.
- Di luar cakupan: fitur lain (search bar, widget tambahan, dsb.).

## Kriteria selesai
- [ ] Setelah login, tampilan sesuai spesifikasi (latar, kartu, grid 6 kolom, baris terakhir rata kiri)
- [ ] Jam berdetak tiap detik, tanpa memory leak
- [ ] Pasang atau uninstall modul → grid ikut berubah tanpa ubah kode
- [ ] User non-admin hanya melihat app yang boleh ia akses
- [ ] Pengumuman tersimpan dan terlihat user lain; user non-admin tidak bisa menyimpan (dicek di server)
- [ ] Layar sempit tidak rusak
- [ ] Upgrade modul sukses, tanpa error di log server maupun console browser
- [ ] `git diff` hanya menyentuh modul custom

## Laporan akhir
1. Daftar file yang dibuat/diubah.
2. Perintah install/upgrade dan cara mengujinya (contoh: `./odoo-bin -d <db> -u home_menu_custom`).
3. Asumsi yang kamu ambil, perbedaan dengan spesifikasi, dan hal yang tidak bisa kamu verifikasi.
