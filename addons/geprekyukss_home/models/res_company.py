# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import AccessError


class ResCompany(models.Model):
    _inherit = "res.company"

    home_menu_announcement = fields.Text(
        string="Home Menu Announcement",
        help="Teks pengumuman yang tampil di halaman awal (Home Menu).",
    )

    def set_home_menu_announcement(self, text):
        """Simpan pengumuman halaman awal.

        Pembatasan hak akses dilakukan di server (bukan hanya di UI): hanya
        anggota grup Settings (base.group_system) yang boleh mengubah.
        """
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                "Hanya pengguna dengan hak Settings yang dapat mengubah pengumuman."
            )
        for company in self:
            company.sudo().write({"home_menu_announcement": text or False})
        return True
