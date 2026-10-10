/** @odoo-module */

import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

export class MemberCard extends Component {
    static template = "geprekyukss_pos.MemberCard";
    static props = {};

    setup() {
        this.pos = usePos();
    }

    get partner() {
        return this.pos.getOrder()?.getPartner();
    }

    get initials() {
        const p = this.partner;
        if (!p || !p.name) {
            return "?";
        }
        return p.name
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((w) => w[0].toUpperCase())
            .join("");
    }

    /**
     * Ganti/pilih member.
     *
     * Sebelumnya: `this.pos.showScreen("PartnerListScreen", {...})` — dua-duanya
     * tidak ada di Odoo 19 (`PosStore` hanya punya `navigate()`, dan tidak ada
     * halaman bernama `PartnerListScreen`), jadi klik kartu member melempar
     * TypeError. API resmi Odoo 19 untuk memilih pelanggan adalah
     * `pos.selectPartner()` → membuka popup `PartnerList` bawaan dan langsung
     * memasang mitra terpilih ke order aktif.
     */
    async selectCustomer() {
        await this.pos.selectPartner();
    }
}
