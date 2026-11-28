# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class WmAudit(models.Model):
    _name = 'wm.audit'
    _description = 'Waste Management Audit'
    _order = 'event_datetime desc, id desc'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    action = fields.Char(required=True, index=True)
    res_model = fields.Char(index=True)
    res_id = fields.Integer(index=True)
    res_name = fields.Char()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    event_datetime = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    previous_value = fields.Char()
    new_value = fields.Char()
    notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.audit') or 'WM-AUD-NEW'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group('waste_management.group_wm_manager'):
            raise UserError('Audit records cannot be modified.')
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self.env.user.has_group('waste_management.group_wm_manager'):
            raise UserError('Audit records cannot be deleted.')
        return super().unlink()
