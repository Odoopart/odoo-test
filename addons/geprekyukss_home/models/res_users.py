# -*- coding: utf-8 -*-
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        """User baru langsung memakai Home Menu kustom sebagai halaman awal."""
        action = self.env.ref("geprekyukss_home.action_home", raise_if_not_found=False)
        if action:
            for vals in vals_list:
                vals.setdefault("action_id", action.id)
        return super().create(vals_list)
