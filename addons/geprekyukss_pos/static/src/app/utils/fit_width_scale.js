/** @odoo-module **/

const DESIGN_WIDTH = 1280;
const DESIGN_HEIGHT = 800;

// ==== RESPONSIVE: laptop / tablet / mobile ====
// Fluid (default, FULLSCREEN_ALL = true): layout mengikuti layar asli tanpa
// letterbox; class "pos-fluid" ditambahkan ke <body>.
// Letterbox 16:10 (opt-in, FULLSCREEN_ALL = false di layar lebar): --pos-scale
// dihitung dari viewport dan class "pos-letterbox" ditambahkan ke <body>.
//
// Catatan (perbaikan 19 Sep 2026): dulu CSS default-nya letterbox, sehingga
// sebelum JS ini jalan (DOMContentLoaded + beberapa retry) layar sempat tampil
// sebagai kotak 1280x800 di atas latar gelap. Sekarang default CSS = fluid dan
// letterbox hanya aktif kalau class .pos-letterbox memang dipasang di sini.
const FLUID_MAX_WIDTH = 820;

const FULLSCREEN_ALL = true;

function isFluidMode() {
    if (FULLSCREEN_ALL) {
        return true;
    }
    const portrait = window.innerHeight > window.innerWidth;
    return window.innerWidth <= FLUID_MAX_WIDTH || portrait;
}

function applyScale() {
    if (!document.body) {
        return;
    }
    if (isFluidMode()) {
        document.body.classList.add("pos-fluid");
        document.body.classList.remove("pos-letterbox");
        document.body.style.setProperty("--pos-scale", 1);
        return;
    }
    document.body.classList.remove("pos-fluid");
    document.body.classList.add("pos-letterbox");
    const scaleX = window.innerWidth / DESIGN_WIDTH;
    const scaleY = window.innerHeight / DESIGN_HEIGHT;
    const scale = Math.min(scaleX, scaleY);
    document.body.style.setProperty("--pos-scale", scale);
}

window.addEventListener("resize", applyScale);
window.addEventListener("orientationchange", applyScale);
document.addEventListener("DOMContentLoaded", applyScale);

// Mobile Chrome/Safari menyembunyikan/menampilkan address bar saat scroll,
// mengubah window.innerHeight TANPA selalu memicu event "resize" biasa.
// visualViewport API didesain khusus untuk menangkap perubahan ini.
if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", applyScale);
    window.visualViewport.addEventListener("scroll", applyScale);
}

// Recheck beberapa kali setelah load, untuk menangkap viewport yang baru
// "settle" (address bar animasi selesai) setelah render awal.
[100, 300, 800, 1500].forEach((delay) => {
    setTimeout(applyScale, delay);
});

if (document.readyState !== "loading") {
    applyScale();
}
