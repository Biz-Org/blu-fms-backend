# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FmsHelpdeskEscalationLevel(models.Model):
    _name = 'fms.helpdesk.escalation.level'
    _description = 'Escalation Level'
    _inherit = ['fms.helpdesk.config.mixin']
    _order = 'level, id'

    name = fields.Char(required=True, translate=True)
    level = fields.Integer(required=True, default=1)
    description = fields.Text(translate=True)
    owner_type = fields.Selection(
        [('team_lead', "Ticket's Team Lead"),
         ('user', 'Specific User')],
        default='team_lead', required=True)
    user_id = fields.Many2one('res.users', string='Escalation Owner', domain=[('share', '=', False)])
    notify_user_ids = fields.Many2many(
        'res.users', 'fms_helpdesk_escalation_level_notify_rel', 'level_id', 'user_id',
        string='Also Notify', domain=[('share', '=', False)])
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('level_uniq', 'unique(level)', 'Each escalation level number can only be used once.'),
        ('level_positive', 'CHECK(level > 0)', 'The escalation level must be greater than zero.'),
    ]

    @api.constrains('owner_type', 'user_id')
    def _check_owner(self):
        for level in self:
            if level.owner_type == 'user' and not level.user_id:
                raise ValidationError(_("Escalation level '%s' needs an owner user.", level.name))

    def _get_owner(self, ticket):
        self.ensure_one()
        if self.owner_type == 'team_lead':
            return ticket.team_id.leader_id or self.user_id
        return self.user_id
