/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

const { DateTime } = luxon;

// Urutan tile aplikasi:
//   "az"       -> A sampai Z berdasarkan nama (sesuai referensi).
//   "sequence" -> urutan bawaan Odoo (urutan menu).
const APP_ORDER = "az";

/**
 * Jam & tanggal. Komponen terpisah agar pembaruan tiap detik tidak
 * me-render ulang grid aplikasi.
 */
export class HomeClock extends Component {
    static template = "geprekyukss_home.HomeClock";

    setup() {
        this.state = useState({ now: DateTime.local() });
        this.interval = setInterval(() => {
            this.state.now = DateTime.local();
        }, 1000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    get dateLabel() {
        return this.state.now.toLocaleString(DateTime.DATE_FULL);
    }

    get timeLabel() {
        return this.state.now.toLocaleString(DateTime.TIME_WITH_SECONDS);
    }
}

/**
 * Halaman awal: kartu jam + pengumuman, lalu grid ikon aplikasi.
 */
export class HomeMenu extends Component {
    static template = "geprekyukss_home.HomeMenu";
    static components = { HomeClock };

    setup() {
        this.menuService = useService("menu");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            announcement: "",
            canEdit: false,
            saving: false,
        });

        onWillStart(async () => {
            this.state.canEdit = await user.hasGroup("base.group_system");
            const companyId = this.companyId;
            if (companyId) {
                const [company] = await this.orm.read(
                    "res.company",
                    [companyId],
                    ["home_menu_announcement"]
                );
                this.state.announcement = company.home_menu_announcement || "";
            }
        });
    }

    get companyId() {
        return user.activeCompany && user.activeCompany.id;
    }

    get apps() {
        const apps = this.menuService.getApps().filter((app) => app.actionID);
        if (APP_ORDER === "az") {
            return [...apps].sort((a, b) => a.name.localeCompare(b.name));
        }
        return apps;
    }

    get placeholder() {
        return _t("Announcement for everyone");
    }

    get saveLabel() {
        return _t("Save");
    }

    get appIconFallback() {
        return "/web/static/img/default_icon_app.png";
    }

    selectApp(app) {
        this.menuService.selectMenu(app);
    }

    async saveAnnouncement() {
        if (!this.state.canEdit || this.state.saving || !this.companyId) {
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call("res.company", "set_home_menu_announcement", [
                [this.companyId],
                this.state.announcement,
            ]);
            this.notification.add(_t("Pengumuman tersimpan."), { type: "success" });
        } catch (error) {
            this.notification.add(
                (error && error.message) || _t("Gagal menyimpan pengumuman."),
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("actions").add("geprekyukss_home.home", HomeMenu);
