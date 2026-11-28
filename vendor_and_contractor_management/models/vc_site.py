# -*- coding: utf-8 -*-
from odoo import api, fields, models


class VcSite(models.Model):
    _name = 'vc.site'
    _description = 'Vendor Contractor Site'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Site Reference', copy=False, readonly=True, default='New')
    address = fields.Text()
    manager_id = fields.Many2one('res.users', string='Site Manager')
    phone = fields.Char()
    email = fields.Char()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('vc.site') or 'SITE-NEW'
        return super().create(vals_list)
