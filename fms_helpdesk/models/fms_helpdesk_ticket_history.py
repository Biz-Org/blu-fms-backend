# -*- coding: utf-8 -*-

from odoo import fields, models

HISTORY_ACTIONS = [
    ('create', 'Created'),
    ('submit', 'Submitted'),
    ('update', 'Updated'),
    ('status', 'Status Changed'),
    ('category', 'Category Changed'),
    ('priority', 'Priority Changed'),
    ('assignment', 'Assignment Changed'),
    ('comment', 'Comment'),
    ('attachment', 'Attachment'),
    ('sla', 'SLA'),
    ('escalation', 'Escalation'),
    ('resolution', 'Resolution'),
    ('verification', 'Verification'),
    ('closure', 'Closure'),
    ('reopen', 'Reopened'),
    ('feedback', 'Feedback'),
]


class FmsHelpdeskTicketHistory(models.Model):
    _name = 'fms.helpdesk.ticket.history'
    _description = 'Helpdesk Ticket History'
    _inherit = ['fms.helpdesk.audit.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'action'

    ticket_id = fields.Many2one(
        'fms.helpdesk.ticket', string='Ticket', required=True, ondelete='cascade', index=True, readonly=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
    user_id = fields.Many2one(
        'res.users', string='User', default=lambda self: self.env.user, readonly=True, ondelete='set null')
    action = fields.Selection(HISTORY_ACTIONS, required=True, readonly=True, index=True)
    field_name = fields.Char(string='Technical Field', readonly=True)
    field_label = fields.Char(string='Field', readonly=True)
    old_value = fields.Text(string='Previous Value', readonly=True)
    new_value = fields.Text(string='New Value', readonly=True)
    remarks = fields.Text(readonly=True)
