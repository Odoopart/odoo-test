/** @odoo-module */

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export const SPICE_LEVELS = [
    { value: "1", label: "1 🌶️" },
    { value: "2", label: "2 🌶️🌶️" },
    { value: "3", label: "3 🌶️🌶️🌶️" },
    { value: "4", label: "4 🌶️🌶️🌶️🌶️" },
    { value: "5", label: "5 🌶️🌶️🌶️🌶️🌶️" },
];

// Label TEKS untuk badge level pedas di panel order & struk — TANPA emoji/ikon.
//
// Popup pemilihan di atas sengaja tetap memakai emoji (skala visual), sedangkan
// badge di panel order diminta tampil teks saja; markup badge dulu juga memasang
// ikon `<i class="fa fa-fire">`, dan itu sudah dihapus. Bonus: emoji cabe tidak
// selalu bisa dicetak printer struk thermal, sedangkan teks selalu aman.
//
// Kalau kalimatnya mau diubah (mis. "Pedas 3" atau angka saja), ubah di SINI —
// satu tempat ini dipakai badge panel order maupun struk.
export const SPICE_TEXT_LABELS = Object.fromEntries(
    SPICE_LEVELS.map((lvl) => [lvl.value, "Level " + lvl.value])
);

// Popup dibangun di atas komponen Dialog generik dari @web/core (bukan
// service "popup" lama yang sudah dihapus dari POS sejak refactor OWL).
// Dipanggil lewat this.dialog.add(SpiceLevelPopup, { productName, getPayload }).
export class SpiceLevelPopup extends Component {
    static template = "geprekyukss_pos.SpiceLevelPopup";
    static components = { Dialog };
    static props = {
        productName: String,
        close: Function,
        getPayload: Function,
    };

    setup() {
        this.levels = SPICE_LEVELS;
    }

    selectLevel(value) {
        this.props.getPayload(value);
        this.props.close();
    }

    cancel() {
        this.props.getPayload(null);
        this.props.close();
    }
}
