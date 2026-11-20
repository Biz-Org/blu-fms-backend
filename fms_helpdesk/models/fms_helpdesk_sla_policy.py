# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TIME_UNITS = [
    ('minutes', 'Minutes'),
    ('hours', 'Hours'),
    ('days', 'Days'),
]
UNIT_MINUTES = {'minutes': 1, 'hours': 60, 'days': 1440}


class FmsHelpdeskSlaPolicy(models.Model):
    _name = 'fms.helpdesk.sla.policy'
    _description = 'Helpdesk SLA Policy'
    _inherit = ['mail.thread', 'fms.helpdesk.config.mixin']
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True, tracking=True)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    priority_id = fields.Many2one(
        'fms.helpdesk.priority', string='Complaint Priority', required=True,
        ondelete='restrict', tracking=True)
    category_ids = fields.Many2many(
        'fms.helpdesk.category', 'fms_helpdesk_sla_policy_category_rel', 'policy_id', 'category_id',
        string='Categories', check_company=True,
        help="Leave empty to apply the policy to every category.")

    response_target = fields.Integer(required=True, default=1, tracking=True)
    response_unit = fields.Selection(TIME_UNITS, required=True, default='hours', tracking=True)
    resolution_target = fields.Integer(required=True, default=8, tracking=True)
    resolution_unit = fields.Selection(TIME_UNITS, required=True, default='hours', tracking=True)
    response_minutes = fields.Integer(compute='_compute_target_minutes', store=True)
    resolution_minutes = fields.Integer(compute='_compute_target_minutes', store=True)

    coverage = fields.Selection(
        [('business_hours', 'Business Hours'),
         ('24x7', '24x7')],
        default='business_hours', required=True, tracking=True)
    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Business Hours', check_company=True,
        default=lambda self: self.env.company.resource_calendar_id)

    pause_on_pending = fields.Boolean(string='Pause when Pending / Pending Approval')
    pause_on_awaiting_resident = fields.Boolean(string='Pause when Awaiting Resident', default=True)
    pause_on_with_vendor = fields.Boolean(string='Pause when With Vendor', default=True)

    warning_threshold = fields.Integer(
        string='At Risk at (%)', default=80,
        help="Share of the target time after which the SLA becomes At Risk.")
    escalation_level_id = fields.Many2one(
        'fms.helpdesk.escalation.level', string='Escalation Level on Breach', ondelete='set null')
    auto_escalate = fields.Boolean(string='Escalate Automatically on Breach')

    _sql_constraints = [
        ('response_target_positive', 'CHECK(response_target > 0)', 'The response target must be greater than zero.'),
        ('resolution_target_positive', 'CHECK(resolution_target > 0)', 'The resolution target must be greater than zero.'),
        ('warning_threshold_range', 'CHECK(warning_threshold > 0 AND warning_threshold < 100)',
         'The At Risk threshold must be between 1 and 99 percent.'),
    ]

    @api.depends('response_target', 'response_unit', 'resolution_target', 'resolution_unit')
    def _compute_target_minutes(self):
        for policy in self:
            policy.response_minutes = policy.response_target * UNIT_MINUTES.get(policy.response_unit, 0)
            policy.resolution_minutes = policy.resolution_target * UNIT_MINUTES.get(policy.resolution_unit, 0)

    @api.constrains('response_minutes', 'resolution_minutes')
    def _check_targets(self):
        for policy in self:
            if policy.resolution_minutes < policy.response_minutes:
                raise ValidationError(_(
                    "SLA policy '%s': the resolution target cannot be shorter than the response target.",
                    policy.name))

    @api.constrains('coverage', 'resource_calendar_id')
    def _check_calendar(self):
        for policy in self:
            if policy.coverage == 'business_hours' and not policy.resource_calendar_id:
                raise ValidationError(_("SLA policy '%s' uses business hours and needs a working calendar.", policy.name))

    def _get_pause_states(self):
        self.ensure_one()
        states = set()
        if self.pause_on_pending:
            states.add('pending')
        if self.pause_on_awaiting_resident:
            states.add('awaiting_resident')
        if self.pause_on_with_vendor:
            states.add('with_vendor')
        return states

    def _uses_calendar(self):
        self.ensure_one()
        return self.coverage == 'business_hours' and self.resource_calendar_id

    def _plan_deadline(self, start, minutes):
        """Return the UTC datetime reached after `minutes` of SLA time counted from `start`."""
        self.ensure_one()
        if self._uses_calendar():
            deadline = self.sudo().resource_calendar_id.plan_hours(minutes / 60.0, start, compute_leaves=True)
            if deadline:
                return deadline
        return start + timedelta(minutes=minutes)

    def _working_minutes(self, start, end):
        """SLA minutes elapsed between two UTC datetimes."""
        self.ensure_one()
        if not start or not end or end <= start:
            return 0.0
        if self._uses_calendar():
            return self.sudo().resource_calendar_id.get_work_hours_count(start, end, compute_leaves=True) * 60.0
        return (end - start).total_seconds() / 60.0

    @api.model
    def _find_policy(self, priority, category=None, company=None):
        """Most specific active policy for the ticket context: category-specific first, then by sequence."""
        if not priority:
            return self.browse()
        company = company or self.env.company
        domain = [('priority_id', '=', priority.id), ('company_id', 'in', [company.id, False])]
        if category:
            domain += ['|', ('category_ids', '=', False), ('category_ids', 'in', category.ids)]
        else:
            domain += [('category_ids', '=', False)]
        policies = self.search(domain)
        if not policies:
            return policies
        return min(policies, key=lambda p: (0 if category and category in p.category_ids else 1, p.sequence, p.id))
