# -*- coding: utf-8 -*-

from odoo import fields, models


class FmsHelpdeskPriority(models.Model):
    _name = 'fms.helpdesk.priority'
    _description = 'Helpdesk Priority Level'
    _inherit = ['fms.helpdesk.config.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="Stable technical key, e.g. critical, high, medium, low.")
    sequence = fields.Integer(default=10, help="Lower sequence means more urgent.")
    description = fields.Text(translate=True)
    color = fields.Integer()
    is_urgent = fields.Boolean(
        string='High Priority Workload',
        help="Counted as high/critical work on dashboards and triggers staff alerts on creation.")
    escalation_level_id = fields.Many2one(
        'fms.helpdesk.escalation.level', string='Default Escalation Level', ondelete='set null')
    active = fields.Boolean(default=True)
    sla_policy_ids = fields.One2many('fms.helpdesk.sla.policy', 'priority_id', string='SLA Policies')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The priority code must be unique.'),
    ]
