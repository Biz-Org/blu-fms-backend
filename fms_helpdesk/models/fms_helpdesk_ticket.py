# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext

TICKET_STATES = [
    ('draft', 'Draft'),
    ('new', 'New'),
    ('open', 'Open'),
    ('assigned', 'Assigned'),
    ('in_progress', 'In Progress'),
    ('pending', 'Pending'),
    ('awaiting_resident', 'Awaiting Resident'),
    ('with_vendor', 'With Vendor'),
    ('escalated', 'Escalated'),
    ('resolved', 'Resolved'),
    ('awaiting_verification', 'Awaiting Verification'),
    ('closed', 'Closed'),
    ('reopened', 'Reopened'),
]

# Ticket status lifecycle (scope section 8). Draft -> New only happens through submission.
ALLOWED_TRANSITIONS = {
    'draft': set(),
    'new': {'open', 'assigned', 'in_progress', 'closed'},
    'open': {'new', 'assigned', 'in_progress', 'pending', 'escalated', 'closed'},
    'assigned': {'open', 'in_progress', 'pending', 'awaiting_resident', 'with_vendor', 'escalated', 'resolved'},
    'in_progress': {'assigned', 'pending', 'awaiting_resident', 'with_vendor', 'escalated',
                    'resolved', 'awaiting_verification'},
    'pending': {'assigned', 'in_progress', 'escalated', 'resolved'},
    'awaiting_resident': {'in_progress', 'escalated', 'resolved', 'closed'},
    'with_vendor': {'in_progress', 'escalated', 'resolved'},
    'escalated': {'assigned', 'in_progress', 'resolved', 'awaiting_verification'},
    'resolved': {'awaiting_verification', 'in_progress', 'closed'},
    'awaiting_verification': {'in_progress', 'closed'},
    'closed': {'reopened'},
    'reopened': {'assigned', 'in_progress', 'escalated', 'resolved'},
}
DONE_STATES = {'resolved', 'awaiting_verification', 'closed'}
NOT_OPEN_STATES = DONE_STATES | {'draft'}
# Waiting states must NOT count as first response — only real staff work does.
FIRST_RESPONSE_STATES = {'in_progress', 'resolved', 'awaiting_verification', 'escalated'}

SLA_STATUSES = [
    ('on_track', 'On Track'),
    ('at_risk', 'At Risk'),
    ('paused', 'Paused'),
    ('breached', 'Breached'),
    ('completed', 'Completed'),
]
SLA_STATUS_RANK = {'breached': 5, 'at_risk': 4, 'paused': 3, 'on_track': 2, 'completed': 1}
ACTIVE_SLA_STATUSES = ('on_track', 'at_risk')

CLOSURE_REASONS = [
    ('resolved', 'Resolved'),
    ('duplicate', 'Duplicate'),
    ('invalid', 'Invalid / Not a Complaint'),
    ('withdrawn', 'Withdrawn by Resident'),
    ('no_response', 'No Response from Resident'),
    ('other', 'Other'),
]
NO_RESOLUTION_CLOSURE_REASONS = {'duplicate', 'invalid', 'withdrawn', 'no_response'}

# Ticket fields copied into the structured audit trail, with their history action.
HISTORY_FIELDS = {
    'title': 'update',
    'description': 'update',
    'resident_id': 'update',
    'property_name': 'update',
    'building_name': 'update',
    'floor_name': 'update',
    'unit_name': 'update',
    'location_type': 'update',
    'location_detail': 'update',
    'category_id': 'category',
    'subcategory_id': 'category',
    'priority_id': 'priority',
    'team_id': 'assignment',
    'user_id': 'assignment',
    'sla_policy_id': 'sla',
    'attachment_ids': 'attachment',
    'state': 'status',
}
STATE_HISTORY_ACTIONS = {
    'resolved': 'resolution',
    'awaiting_verification': 'resolution',
    'escalated': 'escalation',
    'closed': 'closure',
    'reopened': 'reopen',
}
SLA_TRIGGER_FIELDS = {'state', 'sla_policy_id', 'sla_start_date', 'first_response_date', 'resolved_date'}

ASSIGN_FIELDS = {'team_id', 'user_id'}
RESIDENT_WRITE_FIELDS = {
    'title', 'description', 'attachment_ids',
    'contact_name', 'contact_phone', 'contact_email', 'preferred_contact_method',
    'property_name', 'building_name', 'floor_name', 'unit_name',
    'location_type', 'location_detail', 'preferred_visit_date', 'visit_notes',
}
RESIDENT_CREATE_FIELDS = RESIDENT_WRITE_FIELDS | {
    'category_id', 'subcategory_id', 'priority_id', 'resident_id', 'channel',
    'company_id', 'state', 'reported_by_id',
}


class FmsHelpdeskTicket(models.Model):
    _name = 'fms.helpdesk.ticket'
    _description = 'Helpdesk Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'fms.helpdesk.access.mixin']
    _order = 'id desc'
    _rec_names_search = ['name', 'title']
    _check_company_auto = True

    # Identification
    name = fields.Char(string='Ticket ID', readonly=True, copy=False, index='trigram')
    title = fields.Char(string='Complaint Title', required=True, tracking=True)
    description = fields.Html()
    state = fields.Selection(
        TICKET_STATES, string='Status', default='new', required=True,
        tracking=True, index=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True)
    channel = fields.Selection(
        [('helpdesk', 'Helpdesk Desk'),
         ('portal', 'Resident Portal'),
         ('mobile', 'Mobile App'),
         ('phone', 'Phone'),
         ('email', 'Email'),
         ('walk_in', 'Walk-in')],
        default='helpdesk', required=True)
    reported_by_id = fields.Many2one(
        'res.users', string='Created By', default=lambda self: self.env.user, ondelete='set null')
    submitted_date = fields.Datetime(readonly=True, copy=False, index=True)

    # Resident and contact
    resident_id = fields.Many2one(
        'res.partner', string='Resident', tracking=True, index=True, check_company=True)
    contact_name = fields.Char(compute='_compute_contact_info', store=True, readonly=False)
    contact_phone = fields.Char(compute='_compute_contact_info', store=True, readonly=False)
    contact_email = fields.Char(compute='_compute_contact_info', store=True, readonly=False)
    preferred_contact_method = fields.Selection(
        [('phone', 'Phone'), ('app', 'App'), ('email', 'Email')], default='app')

    # Location (plain text until a Property / Unit master module exists)
    property_name = fields.Char(string='Property', compute='_compute_location', store=True, readonly=False, index=True)
    building_name = fields.Char(string='Building / Tower', compute='_compute_location', store=True, readonly=False, index=True)
    floor_name = fields.Char(string='Floor', compute='_compute_location', store=True, readonly=False)
    unit_name = fields.Char(string='Apartment / Unit', compute='_compute_location', store=True, readonly=False, index=True)
    location_type = fields.Selection(
        [('apartment_inside', 'Apartment Inside'),
         ('common_area', 'Common Area'),
         ('lift_lobby', 'Lift / Lobby'),
         ('parking', 'Parking'),
         ('terrace', 'Terrace / Roof'),
         ('exterior', 'Exterior / Grounds'),
         ('other', 'Other')],
        string='Specific Location', default='apartment_inside')
    location_detail = fields.Char(string='Location Details')
    preferred_visit_date = fields.Datetime(string='Preferred Visit Time')
    visit_notes = fields.Text(string='Visit / Access Notes')

    # Classification
    category_id = fields.Many2one(
        'fms.helpdesk.category', string='Category', tracking=True, index=True,
        check_company=True, ondelete='restrict')
    subcategory_id = fields.Many2one(
        'fms.helpdesk.subcategory', string='Subcategory', tracking=True, index=True, ondelete='restrict',
        domain="[('category_id', '=', category_id)]")
    priority_id = fields.Many2one(
        'fms.helpdesk.priority', string='Priority', compute='_compute_priority_id', store=True,
        readonly=False, tracking=True, index=True, ondelete='restrict')
    is_urgent = fields.Boolean(related='priority_id.is_urgent', store=True, string='High Priority')

    # Assignment
    team_id = fields.Many2one(
        'fms.helpdesk.team', string='Support Team', tracking=True, index=True, check_company=True)
    user_id = fields.Many2one(
        'res.users', string='Assignee', tracking=True, index=True, domain=[('share', '=', False)])
    assigned_date = fields.Datetime(readonly=True, copy=False)
    routing_rule_id = fields.Many2one(
        'fms.helpdesk.routing.rule', string='Applied Routing Rule', readonly=True, copy=False, ondelete='set null')
    assignment_ids = fields.One2many('fms.helpdesk.assignment', 'ticket_id', string='Assignment History')
    reassignment_count = fields.Integer(compute='_compute_reassignment_count', store=True)
    is_open = fields.Boolean(compute='_compute_is_open', store=True, index=True)
    is_unassigned = fields.Boolean(compute='_compute_is_open', store=True, index=True)

    # SLA
    sla_policy_id = fields.Many2one(
        'fms.helpdesk.sla.policy', string='SLA Policy', tracking=True, check_company=True,
        copy=False, ondelete='restrict')
    sla_start_date = fields.Datetime(string='SLA Start', readonly=True, copy=False)
    sla_paused_since = fields.Datetime(readonly=True, copy=False)
    sla_paused_minutes = fields.Float(readonly=True, copy=False, help="SLA minutes spent in paused states.")
    response_paused_minutes = fields.Float(readonly=True, copy=False)
    response_deadline = fields.Datetime(compute='_compute_sla_deadlines', store=True, index=True)
    resolution_deadline = fields.Datetime(compute='_compute_sla_deadlines', store=True, index=True)
    first_response_date = fields.Datetime(readonly=True, copy=False)
    resolved_date = fields.Datetime(readonly=True, copy=False, index=True)
    response_sla_status = fields.Selection(SLA_STATUSES, readonly=True, copy=False, index=True)
    resolution_sla_status = fields.Selection(SLA_STATUSES, readonly=True, copy=False, index=True)
    sla_status = fields.Selection(SLA_STATUSES, string='SLA Status', compute='_compute_sla_status', store=True, index=True)
    sla_breached = fields.Boolean(compute='_compute_sla_status', store=True, index=True)
    sla_remaining_label = fields.Char(string='SLA', compute='_compute_sla_remaining_label')
    response_hours = fields.Float(
        string='Response Time (h)', compute='_compute_durations', store=True, aggregator='avg')
    resolution_hours = fields.Float(
        string='Resolution Time (h)', compute='_compute_durations', store=True, aggregator='avg')

    # Resolution, closure, reopening
    resolution_ids = fields.One2many('fms.helpdesk.resolution', 'ticket_id', string='Resolutions')
    resolution_id = fields.Many2one(
        'fms.helpdesk.resolution', string='Latest Resolution', compute='_compute_resolution_id', store=True)
    resolved_by_id = fields.Many2one(related='resolution_id.resolved_by_id', store=True, string='Resolved By')
    closed_date = fields.Datetime(readonly=True, copy=False, index=True)
    closed_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    closure_reason = fields.Selection(CLOSURE_REASONS, copy=False, tracking=True)
    closure_comment = fields.Text(copy=False)
    reopen_count = fields.Integer(readonly=True, copy=False)
    last_reopen_reason = fields.Text(copy=False)
    last_reopen_date = fields.Datetime(readonly=True, copy=False)

    # Escalation
    escalation_ids = fields.One2many('fms.helpdesk.escalation', 'ticket_id', string='Escalations')
    escalation_level_id = fields.Many2one(
        'fms.helpdesk.escalation.level', string='Current Escalation Level',
        compute='_compute_escalation', store=True)
    is_escalated = fields.Boolean(compute='_compute_escalation', store=True, index=True)

    # Feedback
    feedback_ids = fields.One2many('fms.helpdesk.feedback', 'ticket_id', string='Feedback')
    feedback_state = fields.Selection(
        [('pending', 'Pending'), ('submitted', 'Submitted'), ('reviewed', 'Reviewed')],
        compute='_compute_feedback', store=True)
    rating = fields.Integer(compute='_compute_feedback', store=True, aggregator='avg')

    # Evidence and audit
    attachment_ids = fields.Many2many(
        'ir.attachment', 'fms_helpdesk_ticket_attachment_rel', 'ticket_id', 'attachment_id',
        string='Photos & Documents')
    history_ids = fields.One2many('fms.helpdesk.ticket.history', 'ticket_id', string='History')

    # Create-form preview (evaluated from current category / routing, not stored)
    preview_ticket_label = fields.Char(compute='_compute_create_preview')
    preview_team_id = fields.Many2one('fms.helpdesk.team', compute='_compute_create_preview', string='Target Department')
    preview_user_id = fields.Many2one('res.users', compute='_compute_create_preview', string='Preview Assignee')
    preview_rule_id = fields.Many2one('fms.helpdesk.routing.rule', compute='_compute_create_preview')
    preview_sla_policy_id = fields.Many2one('fms.helpdesk.sla.policy', compute='_compute_create_preview')
    preview_assignment_mode = fields.Char(compute='_compute_create_preview')
    preview_response_label = fields.Char(compute='_compute_create_preview')
    preview_resolution_label = fields.Char(compute='_compute_create_preview')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The Ticket ID must be unique.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('name', 'title')
    def _compute_display_name(self):
        for ticket in self:
            ticket.display_name = f"{ticket.name} - {ticket.title}" if ticket.name else (ticket.title or _('New Ticket'))

    @api.depends('resident_id')
    def _compute_contact_info(self):
        for ticket in self:
            resident = ticket.resident_id
            ticket.contact_name = resident.name or ticket.contact_name
            ticket.contact_phone = resident.phone or resident.mobile or ticket.contact_phone
            ticket.contact_email = resident.email or ticket.contact_email

    @api.depends('resident_id')
    def _compute_location(self):
        for ticket in self:
            resident = ticket.resident_id
            ticket.property_name = resident.fms_property_name or ticket.property_name
            ticket.building_name = resident.fms_building_name or ticket.building_name
            ticket.floor_name = resident.fms_floor_name or ticket.floor_name
            ticket.unit_name = resident.fms_unit_name or ticket.unit_name

    @api.depends('category_id', 'subcategory_id')
    def _compute_priority_id(self):
        default_priority = self._get_default_priority()
        for ticket in self:
            ticket.priority_id = (
                ticket.subcategory_id.default_priority_id
                or ticket.category_id.default_priority_id
                or ticket.priority_id
                or default_priority
            )

    @api.depends(
        'name', 'state', 'category_id', 'subcategory_id', 'priority_id', 'team_id', 'user_id',
        'sla_policy_id', 'category_id.default_team_id', 'category_id.default_user_id',
        'category_id.auto_routing')
    def _compute_create_preview(self):
        Rule = self.env['fms.helpdesk.routing.rule']
        Policy = self.env['fms.helpdesk.sla.policy']
        for ticket in self:
            rule = Rule.browse()
            team = ticket.team_id
            user = ticket.user_id
            policy = ticket.sla_policy_id
            if ticket.state in ('draft', False) or not ticket.submitted_date:
                if ticket.category_id and ticket.category_id.auto_routing:
                    rule = Rule._find_rule(
                        ticket.category_id, ticket.subcategory_id, ticket.priority_id, ticket.company_id)
                if not team:
                    team = rule.team_id or ticket.category_id.default_team_id
                if not user:
                    user = rule.user_id or ticket.category_id.default_user_id
                if not policy:
                    policy = rule.sla_policy_id or Policy._find_policy(
                        ticket.priority_id, ticket.category_id, ticket.company_id)
            ticket.preview_ticket_label = ticket.name or _('TKT-AUTO')
            ticket.preview_rule_id = rule
            ticket.preview_team_id = team
            ticket.preview_user_id = user
            ticket.preview_sla_policy_id = policy
            ticket.preview_assignment_mode = (
                dict(team._fields['assignment_method']._description_selection(self.env)).get(team.assignment_method)
                if team else _('Pending Category Selection'))
            ticket.preview_response_label = (
                _('%s %s', policy.response_target, policy.response_unit) if policy else _('— min'))
            ticket.preview_resolution_label = (
                _('%s %s', policy.resolution_target, policy.resolution_unit) if policy else _('— hrs'))

    @api.depends('sla_status', 'resolution_deadline', 'response_deadline')
    def _compute_sla_remaining_label(self):
        now = fields.Datetime.now()
        labels = dict(SLA_STATUSES)
        for ticket in self:
            if not ticket.sla_status:
                ticket.sla_remaining_label = False
                continue
            if ticket.sla_status in ('breached', 'completed', 'paused', 'at_risk'):
                ticket.sla_remaining_label = labels.get(ticket.sla_status)
                continue
            deadline = ticket.resolution_deadline or ticket.response_deadline
            if not deadline:
                ticket.sla_remaining_label = labels.get(ticket.sla_status)
                continue
            remaining = deadline - now
            minutes = max(int(remaining.total_seconds() // 60), 0)
            hours, mins = divmod(minutes, 60)
            ticket.sla_remaining_label = _('%02d:%02d left', hours, mins) if hours else _('%s min left', mins)

    @api.depends('state', 'user_id')
    def _compute_is_open(self):
        for ticket in self:
            ticket.is_open = ticket.state not in NOT_OPEN_STATES
            ticket.is_unassigned = ticket.is_open and not ticket.user_id

    @api.depends('assignment_ids.assignment_type')
    def _compute_reassignment_count(self):
        for ticket in self:
            ticket.reassignment_count = len(ticket.assignment_ids.filtered(lambda a: a.assignment_type == 'reassign'))

    @api.depends('sla_policy_id', 'sla_start_date', 'sla_paused_minutes', 'response_paused_minutes')
    def _compute_sla_deadlines(self):
        for ticket in self:
            policy = ticket.sla_policy_id
            if not policy or not ticket.sla_start_date:
                ticket.response_deadline = ticket.resolution_deadline = False
                continue
            start = ticket.sla_start_date
            ticket.response_deadline = policy._plan_deadline(
                start, policy.response_minutes + ticket.response_paused_minutes)
            ticket.resolution_deadline = policy._plan_deadline(
                start, policy.resolution_minutes + ticket.sla_paused_minutes)

    @api.depends('response_sla_status', 'resolution_sla_status')
    def _compute_sla_status(self):
        for ticket in self:
            statuses = [s for s in (ticket.response_sla_status, ticket.resolution_sla_status) if s]
            ticket.sla_status = max(statuses, key=SLA_STATUS_RANK.get) if statuses else False
            ticket.sla_breached = 'breached' in statuses

    @api.depends('submitted_date', 'first_response_date', 'resolved_date')
    def _compute_durations(self):
        for ticket in self:
            start = ticket.submitted_date
            ticket.response_hours = (
                (ticket.first_response_date - start).total_seconds() / 3600.0
                if start and ticket.first_response_date else 0.0)
            ticket.resolution_hours = (
                (ticket.resolved_date - start).total_seconds() / 3600.0
                if start and ticket.resolved_date else 0.0)

    @api.depends('resolution_ids.resolved_date')
    def _compute_resolution_id(self):
        for ticket in self:
            ticket.resolution_id = ticket.resolution_ids.sorted(
                lambda r: (r.resolved_date, r.id), reverse=True)[:1]

    @api.depends('escalation_ids.state', 'escalation_ids.level_id')
    def _compute_escalation(self):
        for ticket in self:
            active = ticket.escalation_ids.filtered(lambda e: e.state in ('open', 'in_progress'))
            ticket.escalation_level_id = active.sorted(lambda e: e.level_id.level, reverse=True)[:1].level_id
            ticket.is_escalated = bool(active)

    @api.depends('feedback_ids.state', 'feedback_ids.rating_value')
    def _compute_feedback(self):
        for ticket in self:
            latest = ticket.feedback_ids.sorted(lambda f: (f.request_date, f.id), reverse=True)[:1]
            ticket.feedback_state = latest.state or False
            ticket.rating = latest.rating_value

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('category_id', 'subcategory_id')
    def _check_subcategory(self):
        for ticket in self:
            if ticket.subcategory_id and ticket.subcategory_id.category_id != ticket.category_id:
                raise ValidationError(_(
                    "Ticket '%(ticket)s': subcategory '%(sub)s' does not belong to category '%(cat)s'.",
                    ticket=ticket.display_name, sub=ticket.subcategory_id.name, cat=ticket.category_id.name))

    @api.constrains('team_id', 'user_id')
    def _check_assignee_in_team(self):
        Team = self.env['fms.helpdesk.team']
        for ticket in self:
            if not Team._check_user_in_team(ticket.team_id, ticket.user_id):
                raise ValidationError(_(
                    "%(user)s is not a member of support team '%(team)s'.",
                    user=ticket.user_id.name, team=ticket.team_id.name))

    @api.constrains('state', 'title', 'category_id', 'priority_id', 'resident_id', 'contact_name')
    def _check_required_on_submit(self):
        for ticket in self.filtered(lambda t: t.state != 'draft'):
            missing = []
            if not ticket.category_id:
                missing.append(_('Category'))
            if not ticket.priority_id:
                missing.append(_('Priority'))
            if not (ticket.resident_id or ticket.contact_name):
                missing.append(_('Resident or Contact Name'))
            if missing:
                raise ValidationError(_(
                    "Ticket '%(ticket)s' cannot be submitted without: %(fields)s.",
                    ticket=ticket.title, fields=', '.join(missing)))

    @api.constrains('state', 'closure_reason', 'resolution_ids')
    def _check_closure(self):
        require_verification = self._get_bool_param('require_verification')
        for ticket in self.filtered(lambda t: t.state == 'closed'):
            if not ticket.closure_reason:
                raise ValidationError(_("Please give a closure reason to close ticket %s.", ticket.name))
            if ticket.closure_reason in NO_RESOLUTION_CLOSURE_REASONS:
                continue
            if not ticket.resolution_ids:
                raise ValidationError(_("Ticket %s cannot be closed before a resolution is recorded.", ticket.name))
            if require_verification and ticket.resolution_id.state != 'verified':
                raise ValidationError(_("Ticket %s needs a verified resolution before closure.", ticket.name))

    @api.constrains('state', 'last_reopen_reason')
    def _check_reopen_reason(self):
        for ticket in self:
            if ticket.state == 'reopened' and not (ticket.last_reopen_reason or '').strip():
                raise ValidationError(_("A reason is required to reopen ticket %s.", ticket.name))

    @api.constrains('attachment_ids')
    def _check_attachments(self):
        for ticket in self:
            self._check_attachment_policy(ticket.attachment_ids)

    @api.model
    def _check_attachment_policy(self, attachments):
        attachments = attachments.sudo()
        if not attachments:
            return
        if self.env.user.share and not self._get_bool_param('allow_resident_attachments'):
            raise ValidationError(_("Residents are not allowed to upload attachments."))
        if len(attachments) > 1 and not self._get_bool_param('allow_multiple_attachments'):
            raise ValidationError(_("Only one attachment is allowed."))
        max_mb = self._get_int_param('max_attachment_size_mb')
        if max_mb and sum(attachments.mapped('file_size')) > max_mb * 1024 * 1024:
            raise ValidationError(_("Attachments exceed the allowed total size of %s MB.", max_mb))
        allowed = {
            ext.strip().lower().lstrip('.')
            for ext in (self._get_param('allowed_attachment_types') or '').split(',') if ext.strip()
        }
        if allowed:
            invalid = attachments.filtered(
                lambda a: '.' not in (a.name or '') or a.name.rsplit('.', 1)[1].lower() not in allowed)
            if invalid:
                raise ValidationError(_(
                    "File type not allowed: %(files)s. Allowed types: %(types)s.",
                    files=', '.join(invalid.mapped('name')), types=', '.join(sorted(allowed))))

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------

    def _check_ticket_privileges(self, vals, tickets=None):
        """Block assignment, escalation, closure, reopening and resident overreach."""
        if self._fms_skip_privilege():
            return
        tickets = tickets if tickets is not None else self
        is_resident = self._fms_is_resident()
        is_lead = self._fms_is_team_lead()
        is_agent = self._fms_is_agent()
        if not (is_resident or is_agent):
            self._fms_raise(_("create or update helpdesk tickets"))

        if is_resident and not is_agent:
            creating = not tickets
            drafts = creating or all(ticket.state == 'draft' for ticket in tickets)
            allowed = set(RESIDENT_CREATE_FIELDS if drafts else RESIDENT_WRITE_FIELDS)
            if vals.get('state') == 'new' and drafts:
                allowed.add('state')
            if self.env.context.get('fms_from_verification') and vals.get('state') == 'in_progress':
                allowed.add('state')
            forbidden = set(vals) - allowed
            if forbidden:
                self._fms_raise(_("change %s on a resident ticket") % ', '.join(sorted(forbidden)))
            if tickets and any(not self._fms_owns_ticket(ticket) for ticket in tickets):
                self._fms_raise(_("update another resident's ticket"))

        creating = not tickets
        if not is_lead:
            if creating:
                for name in ASSIGN_FIELDS:
                    vals.pop(name, None)
            elif any(vals.get(name) for name in ASSIGN_FIELDS if name in vals):
                self._fms_raise(_("assign or reassign tickets"))
        new_state = vals.get('state')
        if new_state == 'escalated' and not is_lead:
            self._fms_raise(_("escalate tickets"))
        if new_state == 'closed' and not is_lead:
            self._fms_raise(_("close tickets"))
        if new_state == 'reopened' and not is_lead:
            self._fms_raise(_("reopen tickets"))

    def unlink(self):
        if not self.env.su and not self._fms_is_admin():
            self._fms_raise(_("delete tickets"))
        # Allow cascading cleanup of append-only history/assignment lines.
        return super(FmsHelpdeskTicket, self.with_context(fms_allow_audit_unlink=True)).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if self._fms_is_resident() and not self.env.su:
            partner_id = self.env.user.partner_id.id
            for vals in vals_list:
                if vals.get('resident_id') and vals['resident_id'] != partner_id:
                    self._fms_raise(_("create tickets for another resident"))
                vals['resident_id'] = partner_id
                self._check_ticket_privileges(vals, tickets=self.browse())
        elif not self._fms_skip_privilege():
            for vals in vals_list:
                self._check_ticket_privileges(vals, tickets=self.browse())
        tickets = super().create(vals_list)
        tickets._link_attachments()
        tickets._log_history('create', remarks=_('Ticket created'))
        initial = [
            {
                'ticket_id': ticket.id,
                'team_id': ticket.team_id.id,
                'user_id': ticket.user_id.id,
                'assignment_type': 'initial',
                'assigned_by_id': self.env.uid,
            }
            for ticket in tickets if ticket.team_id or ticket.user_id
        ]
        if initial:
            self.env['fms.helpdesk.assignment'].sudo().create(initial)
            tickets.filtered('user_id').with_context(fms_internal_write=True).write(
                {'assigned_date': fields.Datetime.now()})
        tickets.filtered(lambda t: t.state != 'draft')._submit()
        return tickets

    def write(self, vals):
        if self.env.context.get('fms_internal_write'):
            return super().write(vals)

        self._check_ticket_privileges(vals, tickets=self)

        if 'state' in vals:
            self._check_state_transition(vals['state'])
        if 'user_id' in vals:
            self._check_reassign_reason(vals['user_id'])

        tracked = [name for name in HISTORY_FIELDS if name in vals]
        old_values = {ticket.id: {name: ticket._format_history_value(name) for name in tracked} for ticket in self}
        old_states = {ticket.id: ticket.state for ticket in self}
        old_owners = {ticket.id: (ticket.team_id, ticket.user_id) for ticket in self}

        result = super().write(vals)

        if 'attachment_ids' in vals:
            self._link_attachments()
        self._log_changes(old_values)
        if 'team_id' in vals or 'user_id' in vals:
            self._record_assignments(old_owners, state_given='state' in vals)
        if 'state' in vals:
            self._on_state_change(old_states)
        if {'priority_id', 'category_id', 'subcategory_id'} & set(vals) and 'sla_policy_id' not in vals:
            self._refresh_sla_policy()
        if SLA_TRIGGER_FIELDS & set(vals):
            self._update_sla_status()
        return result

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        if kwargs.get('message_type') == 'comment':
            body = html2plaintext(kwargs.get('body') or '').strip()
            self._log_history('comment', remarks=body[:2000] or False)
            if message.attachment_ids:
                self._log_history(
                    'attachment', new_value=', '.join(message.attachment_ids.mapped('name')),
                    remarks=_('Added with a comment'))
            is_public_reply = kwargs.get('subtype_xmlid') == 'mail.mt_comment'
            if (is_public_reply and self.submitted_date and not self.first_response_date
                    and not self.env.user.share and self.env.user.partner_id != self.resident_id):
                self.with_context(fms_internal_write=True).write({'first_response_date': fields.Datetime.now()})
                self._update_sla_status()
        return message

    # ------------------------------------------------------------------
    # Submission, routing and assignment
    # ------------------------------------------------------------------

    def action_submit(self):
        drafts = self.filtered(lambda t: t.state == 'draft')
        drafts.with_context(fms_skip_state_check=True).write({'state': 'new'})
        drafts._submit()
        if len(self) != 1:
            return True
        return {
            'type': 'ir.actions.act_window',
            'name': _('Complaint'),
            'res_model': 'fms.helpdesk.ticket',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_save_draft(self):
        """Keep the ticket as a draft. The standard Save already stores the record."""
        for ticket in self.filtered(lambda t: not t.state or t.state == 'new' and not t.submitted_date):
            if ticket.state != 'draft':
                ticket.with_context(fms_skip_state_check=True).write({'state': 'draft'})
        return True

    def action_start_progress(self):
        for ticket in self:
            if ticket.state in ('new', 'open', 'assigned', 'reopened'):
                ticket.write({'state': 'in_progress'})
        return True

    def action_assign(self, team_id=None, user_id=None, reason=False):
        if not self._fms_is_team_lead():
            self._fms_raise(_("assign or reassign tickets"))
        vals = {}
        if team_id:
            vals['team_id'] = team_id
        if user_id:
            vals['user_id'] = user_id
        if not vals:
            raise UserError(_("Select a support team or a staff member to assign."))
        self.with_context(
            fms_assignment_type='manual',
            fms_assignment_reason=reason or False,
        ).write(vals)
        return True

    def action_close(self, reason='resolved', comment=False):
        self.write({
            'state': 'closed',
            'closure_reason': reason,
            'closure_comment': comment or False,
        })
        return True

    def action_reopen(self, reason):
        """Return a closed ticket to work. The window and reason checks stay on the model."""
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_("A reason is required to reopen a ticket."))
        self.write({'state': 'reopened', 'last_reopen_reason': reason})
        return True

    def action_escalate(self, level_id=None, reason='manual', comment=False):
        """Manual escalation. Automatic breaches use ``_escalate_sla_breach``."""
        self.ensure_one()
        if not self._fms_is_team_lead():
            self._fms_raise(_("escalate tickets"))
        if self.state in ('draft', 'closed'):
            raise UserError(_("Draft or closed tickets cannot be escalated."))
        Level = self.env['fms.helpdesk.escalation.level']
        level = Level.browse(int(level_id)) if level_id else (
            self.priority_id.escalation_level_id or self.sla_policy_id.escalation_level_id or Level.search([], limit=1)
        )
        if not level:
            raise UserError(_("Configure an escalation level before escalating this ticket."))
        return self.env['fms.helpdesk.escalation'].create({
            'ticket_id': self.id,
            'level_id': level.id,
            'reason': reason or 'manual',
            'trigger_type': 'manual',
            'comment': comment or False,
        })

    def action_add_resolution(self, description, work_performed=False):
        """Record the solution. Verification and the next status are decided by the resolution model."""
        self.ensure_one()
        text = (description or '').strip()
        if not text:
            raise UserError(_("A resolution is required."))
        html = text if text.startswith('<') else '<p>%s</p>' % text.replace('\n', '<br/>')
        return self.env['fms.helpdesk.resolution'].create({
            'ticket_id': self.id,
            'description': html,
            'work_performed': work_performed or False,
        })

    def _submit(self):
        """Give the ticket its ID, route it, attach the SLA policy and start the SLA timers."""
        Rule = self.env['fms.helpdesk.routing.rule'].sudo()
        Policy = self.env['fms.helpdesk.sla.policy'].sudo()
        auto_routing = self._get_bool_param('auto_routing')
        now = fields.Datetime.now()
        for ticket in self.filtered(lambda t: not t.submitted_date):
            vals = {'submitted_date': now, 'sla_start_date': now}
            if not ticket.name:
                number = self.env['ir.sequence'].sudo().with_company(ticket.company_id).next_by_code('fms.helpdesk.ticket')
                if not number:
                    raise UserError(_("The ticket numbering sequence 'fms.helpdesk.ticket' is missing."))
                vals['name'] = number

            team, user = ticket.team_id, ticket.user_id
            rule = Rule.browse()
            if not team:
                category = ticket.category_id
                if auto_routing and category.auto_routing:
                    rule = Rule._find_rule(category, ticket.subcategory_id, ticket.priority_id, ticket.company_id)
                if rule:
                    team, user = rule.team_id, rule.user_id
                else:
                    team, user = category.default_team_id, category.default_user_id
            if team and not user:
                user = team._get_next_assignee()
                if user:
                    team.sudo().last_assigned_user_id = user

            policy = (
                ticket.sla_policy_id
                or rule.sla_policy_id
                or Policy._find_policy(ticket.priority_id, ticket.category_id, ticket.company_id)
            )
            vals.update(team_id=team.id, user_id=user.id, routing_rule_id=rule.id, sla_policy_id=policy.id)
            if ticket.state == 'new':
                vals['state'] = 'assigned' if user else ('open' if team else 'new')
            ticket.with_context(
                fms_skip_state_check=True,
                fms_assignment_type='auto',
                fms_assignment_reason=rule and _('Routing rule: %s', rule.name) or False,
            ).write(vals)
            ticket._log_history('submit', new_value=ticket.name)
            ticket._notify_urgent_created()
        self._update_sla_status()

    def _notify_urgent_created(self):
        """Staff alert when a High/Critical ticket is submitted (§12)."""
        self.ensure_one()
        if not self.is_urgent:
            return
        subject = _('High/Critical ticket %(ticket)s', ticket=self.name or self.display_name)
        body = _(
            '%(priority)s ticket %(ticket)s — %(title)s was submitted. Assignee: %(user)s.',
            priority=self.priority_id.name or _('Urgent'),
            ticket=self.name or self.display_name,
            title=self.title or '',
            user=self.user_id.name or self.team_id.leader_id.name or _('Unassigned'),
        )
        partners = (self.user_id.partner_id | self.team_id.leader_id.partner_id).filtered(lambda p: p)
        self.message_post(
            body=body, subject=subject, partner_ids=partners.ids,
            message_type='notification', subtype_xmlid='mail.mt_note')
        user = self.user_id or self.team_id.leader_id
        if user:
            try:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=subject,
                    note=body,
                )
            except Exception:
                pass

    def _check_state_transition(self, new_state):
        if self.env.context.get('fms_skip_state_check'):
            return
        state_labels = dict(TICKET_STATES)
        for ticket in self:
            if ticket.state == new_state:
                continue
            if new_state not in ALLOWED_TRANSITIONS.get(ticket.state, set()):
                raise UserError(_(
                    "Ticket %(ticket)s cannot move from %(old)s to %(new)s.",
                    ticket=ticket.display_name, old=state_labels[ticket.state], new=state_labels[new_state]))
            if new_state == 'reopened':
                ticket._check_reopen_allowed()

    def _check_reopen_allowed(self):
        self.ensure_one()
        if not self._get_bool_param('allow_reopen'):
            raise UserError(_("Reopening closed tickets is disabled in Helpdesk Settings."))
        days = self._get_int_param('reopen_days')
        if days and self.closed_date and fields.Datetime.now() > self.closed_date + timedelta(days=days):
            raise UserError(_(
                "Ticket %(ticket)s was closed more than %(days)s days ago and can no longer be reopened.",
                ticket=self.name, days=days))

    def _check_reassign_reason(self, new_user_id):
        if self.env.context.get('fms_assignment_reason') or not self._get_bool_param('reassign_reason_required'):
            return
        if any(ticket.user_id and ticket.user_id.id != new_user_id for ticket in self):
            raise UserError(_("A reason is required to reassign a ticket."))

    def _record_assignments(self, old_owners, state_given=False):
        context = self.env.context
        now = fields.Datetime.now()
        vals_list = []
        for ticket in self:
            old_team, old_user = old_owners[ticket.id]
            if (old_team, old_user) == (ticket.team_id, ticket.user_id):
                continue
            if not (ticket.team_id or ticket.user_id):
                assignment_type = 'unassign'
            elif context.get('fms_assignment_type'):
                assignment_type = context['fms_assignment_type']
            else:
                assignment_type = 'reassign' if (old_team or old_user) else 'manual'
            vals_list.append({
                'ticket_id': ticket.id,
                'team_id': ticket.team_id.id,
                'user_id': ticket.user_id.id,
                'previous_team_id': old_team.id,
                'previous_user_id': old_user.id,
                'assignment_type': assignment_type,
                'reason': context.get('fms_assignment_reason') or False,
                'assigned_by_id': self.env.uid,
            })
            if ticket.user_id != old_user:
                ticket.with_context(fms_internal_write=True).write(
                    {'assigned_date': now if ticket.user_id else False})
            if not state_given:
                if ticket.user_id and ticket.state in ('new', 'open'):
                    ticket.with_context(fms_skip_state_check=True).write({'state': 'assigned'})
                elif not ticket.user_id and ticket.state == 'assigned':
                    ticket.with_context(fms_skip_state_check=True).write({'state': 'open'})
        if vals_list:
            self.env['fms.helpdesk.assignment'].sudo().create(vals_list)

    def _on_state_change(self, old_states):
        now = fields.Datetime.now()
        for ticket in self:
            old, new = old_states[ticket.id], ticket.state
            if old == new:
                continue
            vals = {}
            if new in FIRST_RESPONSE_STATES and not ticket.first_response_date and ticket.submitted_date:
                vals['first_response_date'] = now
            if new in ('resolved', 'awaiting_verification') and not ticket.resolved_date:
                vals['resolved_date'] = now
            if old in DONE_STATES and new not in DONE_STATES:
                vals['resolved_date'] = False
            if new == 'closed':
                vals.update(closed_date=now, closed_by_id=self.env.uid)
            if new == 'reopened':
                vals.update(
                    reopen_count=ticket.reopen_count + 1, last_reopen_date=now,
                    closed_date=False, closed_by_id=False, closure_reason=False)

            policy = ticket.sla_policy_id
            if policy:
                pause_states = policy._get_pause_states()
                if new in pause_states and old not in pause_states:
                    vals['sla_paused_since'] = now
                    ticket._log_history('sla', remarks=_('SLA timer paused (%s)', dict(TICKET_STATES)[new]))
                elif old in pause_states and new not in pause_states and ticket.sla_paused_since:
                    paused = policy._working_minutes(ticket.sla_paused_since, now)
                    vals.update(sla_paused_since=False, sla_paused_minutes=ticket.sla_paused_minutes + paused)
                    if not ticket.first_response_date:
                        vals['response_paused_minutes'] = ticket.response_paused_minutes + paused
                    ticket._log_history('sla', remarks=_('SLA timer resumed after %s minutes', round(paused)))
            if vals:
                ticket.with_context(fms_internal_write=True).write(vals)
            if new == 'closed':
                ticket._request_feedback()

    def _link_attachments(self):
        for ticket in self:
            ticket.attachment_ids.sudo().filtered(lambda a: not a.res_id).write(
                {'res_model': self._name, 'res_id': ticket.id})

    def _request_feedback(self):
        if not self._get_bool_param('feedback_enabled'):
            return
        Feedback = self.env['fms.helpdesk.feedback'].sudo()
        for ticket in self:
            if ticket.closure_reason in NO_RESOLUTION_CLOSURE_REASONS:
                continue
            # Resident master record OR typed contact name (walk-in / Admin create).
            if not ticket.resident_id and not (ticket.contact_name or '').strip():
                continue
            if not ticket.feedback_ids.filtered(lambda f: f.state == 'pending'):
                Feedback.create({'ticket_id': ticket.id})
                ticket._log_history('feedback', remarks=_('Feedback requested from resident'))

    # ------------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------------

    def _refresh_sla_policy(self):
        Policy = self.env['fms.helpdesk.sla.policy']
        for ticket in self.filtered(lambda t: t.submitted_date and t.state != 'closed'):
            rule = ticket.routing_rule_id
            if rule.sla_policy_id and rule._matches(ticket.category_id, ticket.subcategory_id, ticket.priority_id):
                policy = rule.sla_policy_id
            else:
                policy = Policy._find_policy(ticket.priority_id, ticket.category_id, ticket.company_id)
            if policy != ticket.sla_policy_id:
                ticket.write({'sla_policy_id': policy.id})

    def _update_sla_status(self):
        now = fields.Datetime.now()
        labels = dict(SLA_STATUSES)
        transitioned = self.browse()
        for ticket in self:
            old_overall = ticket.sla_status
            policy = ticket.sla_policy_id
            if not policy or not ticket.sla_start_date:
                new_values = {'response_sla_status': False, 'resolution_sla_status': False}
            else:
                new_values = {
                    'response_sla_status': ticket._get_target_status(
                        ticket.response_deadline,
                        ticket.first_response_date or ticket.closed_date,
                        policy.response_minutes + ticket.response_paused_minutes, now),
                    'resolution_sla_status': ticket._get_target_status(
                        ticket.resolution_deadline,
                        ticket.resolved_date or ticket.closed_date,
                        policy.resolution_minutes + ticket.sla_paused_minutes, now),
                }
            changes = {name: value for name, value in new_values.items() if ticket[name] != value}
            if not changes:
                continue
            for name, value in changes.items():
                ticket._log_history(
                    'sla', field_name=name,
                    old_value=labels.get(ticket[name], ''), new_value=labels.get(value, ''))
            ticket.with_context(fms_internal_write=True).write(changes)
            if ticket.sla_status != old_overall:
                ticket._notify_sla_transition(old_overall, ticket.sla_status)
                transitioned |= ticket
        transitioned.filtered(lambda ticket: ticket.sla_status == 'breached')._escalate_sla_breach()

    def _escalate_sla_breach(self):
        """Open one automatic escalation when the SLA policy says a breach must escalate."""
        Escalation = self.env['fms.helpdesk.escalation'].sudo()
        for ticket in self:
            policy = ticket.sla_policy_id
            level = policy.escalation_level_id
            if not policy.auto_escalate or not level:
                continue
            if ticket.state in ('draft', 'closed', 'resolved', 'awaiting_verification'):
                continue
            if ticket.escalation_ids.filtered(
                    lambda escalation: escalation.level_id == level and escalation.state in ('open', 'in_progress')):
                continue
            Escalation.create({
                'ticket_id': ticket.id,
                'level_id': level.id,
                'reason': 'sla_breached',
                'trigger_type': 'automatic',
                'comment': _('Automatic escalation because the SLA was breached.'),
            })

    def _notify_sla_transition(self, old_status, new_status):
        self.ensure_one()
        if new_status not in ('at_risk', 'breached'):
            return
        labels = dict(SLA_STATUSES)
        status_label = labels.get(new_status, new_status)
        # Global critical-warning % (Settings) escalates the At Risk notice wording.
        if new_status == 'at_risk':
            critical = self._get_int_param('sla_critical_warning_percent') or 90
            policy = self.sla_policy_id
            deadline = self.resolution_deadline or self.response_deadline
            total = (policy.resolution_minutes + self.sla_paused_minutes) if policy and self.resolution_deadline else (
                (policy.response_minutes + self.response_paused_minutes) if policy else 0)
            if policy and deadline and total:
                remaining = policy._working_minutes(fields.Datetime.now(), deadline)
                used_pct = (1 - remaining / total) * 100 if total else 0
                if used_pct >= critical:
                    status_label = _('Critical Warning')
        subject = _(
            'SLA %(status)s on %(ticket)s',
            status=status_label, ticket=self.name or self.display_name)
        body = _(
            'Ticket %(ticket)s — %(title)s moved from %(old)s to %(new)s. Remaining: %(sla)s.',
            ticket=self.name or self.display_name,
            title=self.title or '',
            old=labels.get(old_status) or _('None'),
            new=status_label,
            sla=self.sla_remaining_label or '—',
        )
        partners = (self.user_id.partner_id | self.team_id.leader_id.partner_id).filtered(lambda p: p)
        self.message_post(
            body=body, subject=subject, partner_ids=partners.ids,
            message_type='notification', subtype_xmlid='mail.mt_note')
        user = self.user_id or self.team_id.leader_id
        if user:
            existing = self.activity_ids.filtered(
                lambda a: a.user_id == user and a.summary == subject and a.activity_type_id == self.env.ref(
                    'mail.mail_activity_data_warning', raise_if_not_found=False))
            if not existing:
                try:
                    self.activity_schedule(
                        'mail.mail_activity_data_warning',
                        user_id=user.id,
                        summary=subject,
                        note=body,
                    )
                except Exception:
                    # Activity type missing in stripped DBs should not block SLA updates.
                    pass

    def _get_target_status(self, deadline, done_date, total_minutes, now):
        self.ensure_one()
        if not deadline:
            return False
        if done_date:
            return 'completed' if done_date <= deadline else 'breached'
        if self.sla_paused_since:
            return 'breached' if self.sla_paused_since > deadline else 'paused'
        if now > deadline:
            return 'breached'
        policy = self.sla_policy_id
        remaining = policy._working_minutes(now, deadline)
        if total_minutes and (1 - remaining / total_minutes) * 100 >= policy.warning_threshold:
            return 'at_risk'
        return 'on_track'

    @api.model
    def _cron_update_sla_status(self):
        """Scheduled SLA monitor: refresh timers, warn, breach and fire configured escalations."""
        tickets = self.search([
            ('sla_policy_id', '!=', False),
            ('submitted_date', '!=', False),
            ('state', 'not in', ('draft', 'closed')),
        ])
        tickets._update_sla_status()
        return len(tickets)

    # ------------------------------------------------------------------
    # Audit history
    # ------------------------------------------------------------------

    def _format_history_value(self, field_name):
        self.ensure_one()
        field = self._fields[field_name]
        value = self[field_name]
        if field.type == 'many2one':
            return value.display_name or ''
        if field.type in ('many2many', 'one2many'):
            return ', '.join(value.mapped('display_name'))
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, '')
        if field.type == 'html':
            return html2plaintext(value or '').strip()
        return '' if value is False else str(value)

    def _log_changes(self, old_values):
        remarks = self.env.context.get('fms_history_remarks')
        vals_list = []
        for ticket in self:
            for field_name, old in old_values[ticket.id].items():
                new = ticket._format_history_value(field_name)
                if old == new:
                    continue
                action = HISTORY_FIELDS[field_name]
                line_remarks = remarks
                if field_name == 'state':
                    action = STATE_HISTORY_ACTIONS.get(ticket.state, 'status')
                    if ticket.state == 'reopened':
                        line_remarks = ticket.last_reopen_reason
                    elif ticket.state == 'closed':
                        line_remarks = ticket.closure_comment or remarks
                elif action == 'assignment':
                    line_remarks = self.env.context.get('fms_assignment_reason') or remarks
                vals_list.append(ticket._prepare_history_vals(action, field_name, old, new, line_remarks))
        if vals_list:
            self.env['fms.helpdesk.ticket.history'].sudo().create(vals_list)

    def _log_history(self, action, field_name=False, old_value=False, new_value=False, remarks=False):
        if not self:
            return
        self.env['fms.helpdesk.ticket.history'].sudo().create([
            ticket._prepare_history_vals(action, field_name, old_value, new_value, remarks) for ticket in self
        ])

    def _prepare_history_vals(self, action, field_name=False, old_value=False, new_value=False, remarks=False):
        self.ensure_one()
        return {
            'ticket_id': self.id,
            'action': action,
            'field_name': field_name or False,
            'field_label': self._fields[field_name].string if field_name else False,
            'old_value': old_value or False,
            'new_value': new_value or False,
            'remarks': remarks or False,
            'user_id': self.env.uid,
        }

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    @api.model
    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(f'fms_helpdesk.{key}', default)

    @api.model
    def _get_bool_param(self, key):
        return str(self._get_param(key) or '').lower() in ('1', 'true', 'yes')

    @api.model
    def _get_int_param(self, key):
        try:
            return int(self._get_param(key) or 0)
        except ValueError:
            return 0

    @api.model
    def _get_default_priority(self):
        Priority = self.env['fms.helpdesk.priority']
        priority_id = self._get_int_param('default_priority_id')
        return Priority.browse(priority_id).exists() if priority_id else Priority
