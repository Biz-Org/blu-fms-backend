# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class FmsHelpdeskTeam(models.Model):
    _name = 'fms.helpdesk.team'
    _description = 'Helpdesk Support Team'
    _inherit = ['mail.thread', 'fms.helpdesk.access.mixin']
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True, tracking=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text(translate=True)
    color = fields.Integer()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    leader_id = fields.Many2one(
        'res.users', string='Team Lead', tracking=True, domain=[('share', '=', False)])
    member_ids = fields.Many2many(
        'res.users', 'fms_helpdesk_team_member_rel', 'team_id', 'user_id',
        string='Members', domain=[('share', '=', False)])
    assignment_method = fields.Selection(
        [('manual', 'Manual'),
         ('round_robin', 'Round Robin'),
         ('balanced', 'Balanced Workload')],
        default='manual', required=True, tracking=True,
        help="How a staff member is picked when a ticket is routed to this team without a specific assignee.")
    last_assigned_user_id = fields.Many2one('res.users', readonly=True, copy=False)
    ticket_ids = fields.One2many('fms.helpdesk.ticket', 'team_id', string='Tickets')
    open_ticket_count = fields.Integer(compute='_compute_open_ticket_count')

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'A support team with this name already exists.'),
    ]

    def _compute_open_ticket_count(self):
        counts = dict(self.env['fms.helpdesk.ticket']._read_group(
            [('team_id', 'in', self.ids), ('is_open', '=', True)], ['team_id'], ['__count']))
        for team in self:
            team.open_ticket_count = counts.get(team, 0)

    def _get_next_assignee(self):
        """Return the member who should receive the next ticket, or an empty recordset."""
        self.ensure_one()
        members = self.member_ids.filtered('active').sorted('id')
        if not members or self.assignment_method == 'manual':
            return self.env['res.users']
        if self.assignment_method == 'round_robin':
            previous = self.last_assigned_user_id
            index = (members.ids.index(previous.id) + 1) % len(members) if previous in members else 0
            return members[index]
        counts = dict(self.env['fms.helpdesk.ticket']._read_group(
            [('user_id', 'in', members.ids), ('is_open', '=', True)], ['user_id'], ['__count']))
        return min(members, key=lambda user: (counts.get(user, 0), user.id))

    def _fms_check_team_config(self):
        if not self._fms_skip_privilege() and not self._fms_is_manager():
            self._fms_raise(_("change support teams"))

    @api.model_create_multi
    def create(self, vals_list):
        self._fms_check_team_config()
        return super().create(vals_list)

    def write(self, vals):
        if list(vals) != ['last_assigned_user_id']:
            self._fms_check_team_config()
        return super().write(vals)

    def unlink(self):
        self._fms_check_team_config()
        return super().unlink()

    @api.model
    def _check_user_in_team(self, team, user):
        """True when no team/user is given, the team has no members yet, or the user is a member."""
        return not (team and user and team.member_ids) or user in team.member_ids
