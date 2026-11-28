# -*- coding: utf-8 -*-
from odoo import api, fields, models


class VcNotification(models.Model):
    _name = 'vc.notification'
    _description = 'Vendor Contractor Notification'
    _order = 'create_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    title = fields.Char(required=True)
    message = fields.Text()
    category = fields.Selection([
        ('document', 'Document'),
        ('contract', 'Contract'),
        ('pass', 'Daily Pass'),
        ('ptw', 'PTW'),
        ('vendor', 'Vendor'),
        ('contractor', 'Contractor'),
        ('sla', 'SLA'),
        ('compliance', 'Compliance'),
        ('general', 'General'),
    ], default='general', index=True)
    severity = fields.Selection([
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ], default='info', index=True)
    res_model = fields.Char()
    res_id = fields.Integer()
    user_id = fields.Many2one('res.users', string='Target User')
    is_read = fields.Boolean(default=False, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('title')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.title

    def action_mark_read(self):
        self.write({'is_read': True})
        return True
