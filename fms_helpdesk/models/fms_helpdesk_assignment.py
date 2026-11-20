# -*- coding: utf-8 -*-

from odoo import fields, models


class FmsHelpdeskAssignment(models.Model):
    _name = 'fms.helpdesk.assignment'
    _description = 'Ticket Assignment History'
    _inherit = ['fms.helpdesk.audit.mixin']
    _order = 'assign_date desc, id desc'
    _rec_name = 'ticket_id'

    ticket_id = fields.Many2one(
        'fms.helpdesk.ticket', string='Ticket', required=True, ondelete='cascade', index=True, readonly=True)
    team_id = fields.Many2one('fms.helpdesk.team', string='Support Team', readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Assignee', readonly=True, index=True)
    previous_team_id = fields.Many2one('fms.helpdesk.team', string='Previous Team', readonly=True)
    previous_user_id = fields.Many2one('res.users', string='Previous Assignee', readonly=True)
    assignment_type = fields.Selection(
        [('initial', 'Initial Assignment'),
         ('auto', 'Automatic Routing'),
         ('manual', 'Manual Assignment'),
         ('reassign', 'Reassignment'),
         ('bulk', 'Bulk Assignment'),
         ('unassign', 'Unassigned')],
        required=True, readonly=True, index=True)
    reason = fields.Text(readonly=True)
    assigned_by_id = fields.Many2one(
        'res.users', string='Assigned By', default=lambda self: self.env.user, readonly=True)
    assign_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
