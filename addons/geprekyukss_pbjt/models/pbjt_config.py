# -*- coding: utf-8 -*-
"""Konfigurasi PBJT per outlet (pos.config)."""
from odoo import api, fields, models


class PbjtOutletConfig(models.Model):
    _name = "pbjt.outlet.config"
    _description = "Konfigurasi PBJT per Outlet"
    _order = "pos_config_id"

    name = fields.Char(compute="_compute_name", store=True)
    pos_config_id = fields.Many2one(
        "pos.config", string="Outlet (POS)", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="pos_config_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    active = fields.Boolean(default=True)

    daerah = fields.Char(
        string="Daerah", default="Kota Makassar",
        help="Wilayah pemungut PBJT (menentukan tarif/perda).",
    )
    perda_ref = fields.Char(
        string="Dasar Hukum", default="Perda Kota Makassar No. 1 Tahun 2024",
    )
    rate = fields.Float(string="Tarif PBJT (%)", default=10.0)
    price_include = fields.Boolean(
        string="Harga Sudah Termasuk PBJT", default=True,
        help="Bila dicentang, harga menu dianggap sudah termasuk PBJT sehingga "
             "PBJT = tarif/(100+tarif) x penjualan. Bila tidak, PBJT ditambahkan "
             "di atas harga (PBJT = tarif% x penjualan).",
    )
    exempt_omzet_month = fields.Monetary(
        string="Batas Bebas PBJT / Periode", currency_field="currency_id",
        default=5000000.0,
        help="Peredaran usaha di bawah/ sama dengan nilai ini tidak dikenakan PBJT "
             "(usaha mikro).",
    )
    tax_id = fields.Many2one("account.tax", string="Pajak PBJT (sale)")
    liability_account_id = fields.Many2one(
        "account.account", string="Akun Utang PBJT"
    )
    note = fields.Text()

    _pos_config_uniq = models.Constraint(
        "unique(pos_config_id)",
        "Satu outlet hanya boleh memiliki satu konfigurasi PBJT.",
    )

    @api.depends("pos_config_id")
    def _compute_name(self):
        for rec in self:
            rec.name = "PBJT - %s" % (rec.pos_config_id.name or "")

    def action_apply_tax_to_pos_products(self):
        """Terapkan pajak PBJT ke semua produk yang dijual di POS.

        Menggantikan pajak jual lama (mis. PPN 12% warisan) dengan pajak PBJT
        yang dikonfigurasi. Idempoten.
        """
        self.ensure_one()
        if not self.tax_id:
            return False
        products = self.env["product.template"].search([("available_in_pos", "=", True)])
        products.write({"taxes_id": [(6, 0, [self.tax_id.id])]})
        return True
