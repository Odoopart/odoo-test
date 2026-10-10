# -*- coding: utf-8 -*-
"""Rekonsiliasi PBJT per outlet & periode (riil vs negoisasi Bapenda)."""
from datetime import timedelta

from odoo import api, fields, models

# State POS yang dianggap penjualan sah (konsisten dgn dashboard_data).
POS_SALE_STATES = ["done", "invoiced", "posted", "paid"]


class PbjtReconciliation(models.Model):
    _name = "pbjt.reconciliation"
    _description = "Rekonsiliasi PBJT per Outlet & Periode"
    _order = "date_from desc, pos_config_id"

    name = fields.Char(compute="_compute_name", store=True)
    config_id = fields.Many2one(
        "pbjt.outlet.config", string="Konfigurasi PBJT",
        required=True, ondelete="cascade",
    )
    pos_config_id = fields.Many2one(
        related="config_id.pos_config_id", string="Outlet (POS)", store=True
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True)
    currency_id = fields.Many2one(related="config_id.currency_id")

    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)

    rate = fields.Float(related="config_id.rate", store=True)
    price_include = fields.Boolean(related="config_id.price_include", store=True)
    exempt_omzet_month = fields.Monetary(
        related="config_id.exempt_omzet_month", currency_field="currency_id"
    )
    perda_ref = fields.Char(related="config_id.perda_ref")

    # --- Hasil hitung (riil) ---
    sales_gross = fields.Monetary(
        string="Penjualan Bruto", compute="_compute_pbjt", store=True,
        help="Total penjualan POS (amount_total) pada periode.",
    )
    dpp = fields.Monetary(
        string="Dasar Pengenaan Pajak (DPP)", compute="_compute_pbjt", store=True,
    )
    real_tax = fields.Monetary(
        string="PBJT Riil", compute="_compute_pbjt", store=True,
        help="PBJT terutang menurut penjualan POS pada periode.",
    )
    is_exempt = fields.Boolean(
        string="Bebas PBJT", compute="_compute_pbjt", store=True,
    )

    # --- Input manual: yang benar-benar dibayar/dinegosiasikan ---
    negotiated_amount = fields.Monetary(
        string="Dibayar ke Bapenda", currency_field="currency_id",
        help="Nilai PBJT yang benar-benar disetorkan/dinegosiasikan ke Bapenda.",
    )
    gap = fields.Monetary(
        string="Selisih (Riil - Dibayar)", compute="_compute_gap", store=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Selesai")], default="draft"
    )
    note = fields.Text()

    @api.depends("pos_config_id", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s | %s s/d %s" % (
                rec.pos_config_id.name or "",
                rec.date_from or "",
                rec.date_to or "",
            )

    def _sales_domain(self):
        self.ensure_one()
        return [
            ("config_id", "=", self.pos_config_id.id),
            ("state", "in", POS_SALE_STATES),
            ("date_order", ">=", str(self.date_from) + " 00:00:00"),
            ("date_order", "<", (self.date_to + timedelta(days=1)).isoformat() + " 00:00:00"),
        ]

    @api.depends(
        "config_id", "date_from", "date_to",
        "rate", "price_include", "exempt_omzet_month",
    )
    def _compute_pbjt(self):
        Order = self.env["pos.order"]
        for rec in self:
            gross = 0.0
            if rec.config_id and rec.pos_config_id and rec.date_from and rec.date_to:
                rows = Order._read_group(rec._sales_domain(), [], ["amount_total:sum"])
                gross = rows[0][0] if rows else 0.0
            rec.sales_gross = gross
            exempt = gross <= (rec.exempt_omzet_month or 0.0)
            rec.is_exempt = exempt
            if exempt or not gross:
                rec.dpp = gross
                rec.real_tax = 0.0
            elif rec.price_include:
                # Harga sudah termasuk PBJT: DPP = bruto / (1 + tarif)
                dpp = gross / (1.0 + (rec.rate or 0.0) / 100.0)
                rec.dpp = dpp
                rec.real_tax = gross - dpp
            else:
                rec.dpp = gross
                rec.real_tax = gross * (rec.rate or 0.0) / 100.0

    @api.depends("real_tax", "negotiated_amount")
    def _compute_gap(self):
        for rec in self:
            rec.gap = (rec.real_tax or 0.0) - (rec.negotiated_amount or 0.0)

    def action_recompute(self):
        """Hitung ulang dari data POS terbaru (store compute tidak reaktif ke
        pos.order baru)."""
        for rec in self:
            rec._compute_pbjt()
            rec._compute_gap()
        return True

    def action_mark_done(self):
        self.write({"state": "done"})
        return True

    @api.model
    def generate_for_period(self, date_from, date_to):
        """Buat/lengkapi rekonsiliasi untuk semua outlet aktif pada periode."""
        configs = self.env["pbjt.outlet.config"].search([("active", "=", True)])
        created = self.browse()
        for cfg in configs:
            rec = self.search(
                [
                    ("config_id", "=", cfg.id),
                    ("date_from", "=", date_from),
                    ("date_to", "=", date_to),
                ],
                limit=1,
            )
            if not rec:
                rec = self.create(
                    {
                        "config_id": cfg.id,
                        "date_from": date_from,
                        "date_to": date_to,
                    }
                )
            else:
                rec._compute_pbjt()
            created |= rec
        return created
