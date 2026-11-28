# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class VcActivity(models.Model):
    _name = 'vc.activity'
    _description = 'Vendor Contractor Audit Activity'
    _order = 'event_datetime desc, id desc'

    name = fields.Char(string='Activity Reference', copy=False, readonly=True, default='New')
    activity_type = fields.Char(required=True, index=True)
    res_model = fields.Char(index=True)
    res_id = fields.Integer(index=True)
    res_name = fields.Char()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    event_datetime = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    site_id = fields.Many2one('vc.site')
    description = fields.Text()
    previous_state = fields.Char()
    new_state = fields.Char()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vc.activity') or 'ACT-NEW'
        return super().create(vals_list)

    def write(self, vals):
        # Immutable for non-managers
        if not self.env.su and not self.env.user.has_group('vendor_and_contractor_management.group_vc_manager'):
            raise UserError('Audit activities cannot be modified.')
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self.env.user.has_group('vendor_and_contractor_management.group_vc_manager'):
            raise UserError('Audit activities cannot be deleted.')
        return super().unlink()
