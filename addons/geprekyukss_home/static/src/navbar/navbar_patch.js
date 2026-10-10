/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    get homeMenuLabel() {
        return _t("Menu");
    },
    openHomeMenu() {
        this.actionService.doAction("geprekyukss_home.action_home");
    },
});
