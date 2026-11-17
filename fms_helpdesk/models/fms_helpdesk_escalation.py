# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ACTIVE_ESCALATION_STATES = ('open', 'in_progress')


class FmsHelpdeskEscalation(models.Model):
    _name = 'fms.helpdesk.escalation'
    _description = 'Ticket Escalation'
    _inherit = ['mail.thread', 'fms.helpdesk.access.mixin']
    _order = 'escalation_date desc, id desc'
    _check_company_auto = True

    ticket_id = fields.Many2one(
        'fms.helpdesk.ticket', string='Ticket', required=True, ondelete='cascade', index=True, check_company=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True, index=True)
    level_id = fields.Many2one(
        'fms.helpdesk.escalation.level', string='Escalation Level', required=True,
        ondelete='restrict', tracking=True)
    level = fields.Integer(related='level_id.level', store=True)
    reason = fields.Selection(
        [('sla_at_risk', 'SLA At Risk'),
         ('sla_breached', 'SLA Breached'),
         ('critical_priority', 'Critical Priority'),
         ('repeated_complaint', 'Repeated Complaint'),
         ('resident_dissatisfied', 'Resident Dissatisfied'),
         ('manual', 'Manual Escalation'),
         ('other', 'Other')],
        required=True, default='manual', tracking=True, index=True)
    trigger_type = fields.Selection(
        [('manual', 'Manual'), ('automatic', 'Automatic (Rule / SLA)')],
        required=True, default='manual')
    owner_id = fields.Many2one(
        'res.users', string='Escalation Owner', compute='_compute_owner', store=True, readonly=False,
        tracking=True, domain=[('share', '=', False)])
    notify_user_ids = fields.Many2many(
        'res.users', 'fms_helpdesk_escalation_notify_rel', 'escalation_id', 'user_id',
        string='Notify', compute='_compute_owner', store=True, readonly=False)
    escalated_by_id = fields.Many2one(
        'res.users', string='Escalated By', default=lambda self: self.env.user, readonly=True)
    escalation_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
    comment = fields.Text()
    state = fields.Selection(
        [('open', 'Open'),
         ('in_progress', 'In Progress'),
         ('resolved', 'Resolved'),
         ('cancelled', 'Cancelled')],
        default='open', required=True, tracking=True, index=True)
    resolved_date = fields.Datetime(readonly=True, copy=False)
    resolution_note = fields.Text()
    duration_hours = fields.Float(
        string='Escalation Resolution Time (h)', compute='_compute_duration', store=True, aggregator='avg')

    @api.depends('ticket_id.name', 'level_id.name')
    def _compute_display_name(self):
        for escalation in self:
            escalation.display_name = f"{escalation.ticket_id.name or ''} / {escalation.level_id.name or ''}"

    @api.depends('level_id', 'ticket_id.team_id')
    def _compute_owner(self):
        for escalation in self:
            level = escalation.level_id
            escalation.owner_id = level._get_owner(escalation.ticket_id) if level else escalation.owner_id
            escalation.notify_user_ids = level.notify_user_ids

    @api.depends('escalation_date', 'resolved_date')
    def _compute_duration(self):
        for escalation in self:
            escalation.duration_hours = (
                (escalation.resolved_date - escalation.escalation_date).total_seconds() / 3600.0
                if escalation.resolved_date else 0.0)

    @api.constrains('ticket_id', 'level_id', 'state')
    def _check_unique_active_level(self):
        for escalation in self.filtered(lambda e: e.state in ACTIVE_ESCALATION_STATES):
            duplicates = escalation.ticket_id.escalation_ids.filtered(
                lambda e: e != escalation and e.level_id == escalation.level_id
                and e.state in ACTIVE_ESCALATION_STATES)
            if duplicates:
                raise ValidationError(_(
                    "Ticket %(ticket)s already has an active escalation at %(level)s.",
                    ticket=escalation.ticket_id.name, level=escalation.level_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        if not self._fms_skip_privilege() and not self._fms_is_team_lead():
            self._fms_raise(_("escalate tickets"))
        escalations = super().create(vals_list)
        reasons = dict(self._fields['reason']._description_selection(self.env))
        for escalation in escalations:
            ticket = escalation.ticket_id
            if ticket.state in ('draft', 'closed'):
                raise ValidationError(_("Draft or closed tickets cannot be escalated."))
            ticket._log_history(
                'escalation', new_value=escalation.level_id.name,
                remarks=' - '.join(filter(None, [reasons.get(escalation.reason), escalation.comment])))
            if ticket.state not in ('escalated', 'resolved', 'awaiting_verification'):
                ticket.with_context(fms_history_remarks=reasons.get(escalation.reason)).write({'state': 'escalated'})
            escalation._notify_assigned()
        return escalations

    def _notify_assigned(self):
        self.ensure_one()
        ticket = self.ticket_id
        subject = _('Escalation %(level)s on %(ticket)s', level=self.level_id.name, ticket=ticket.name)
        body = _(
            '%(ticket)s was escalated (%(reason)s). Owner: %(owner)s.',
            ticket=ticket.name, reason=dict(self._fields['reason'].selection).get(self.reason, self.reason),
            owner=self.owner_id.name or _('Unassigned'))
        partners = (self.owner_id.partner_id | self.notify_user_ids.mapped('partner_id') | ticket.user_id.partner_id)
        partners = partners.filtered(lambda p: p)
        ticket.message_post(
            body=body, subject=subject, partner_ids=partners.ids,
            message_type='notification', subtype_xmlid='mail.mt_note')
        if self.owner_id:
            try:
                ticket.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=self.owner_id.id,
                    summary=subject,
                    note=body,
                )
            except Exception:
                pass

    def write(self, vals):
        if not self._fms_skip_privilege() and not self._fms_is_team_lead():
            self._fms_raise(_("update an escalation"))
        if vals.get('state') == 'resolved':
            vals.setdefault('resolved_date', fields.Datetime.now())
        result = super().write(vals)
        if vals.get('state') in ('resolved', 'cancelled'):
            for escalation in self:
                ticket = escalation.ticket_id
                ticket._log_history(
                    'escalation', old_value=escalation.level_id.name,
                    new_value=dict(self._fields['state']._description_selection(self.env))[escalation.state],
                    remarks=escalation.resolution_note)
                if ticket.state == 'escalated' and not ticket.is_escalated:
                    ticket.write({'state': 'in_progress'})
        return result
