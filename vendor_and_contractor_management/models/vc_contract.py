# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcContract(models.Model):
    _name = 'vc.contract'
    _description = 'Vendor / Contractor Contract & AMC'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Contract Title', required=True, tracking=True)
    code = fields.Char(string='Contract ID', copy=False, readonly=True, default='New', tracking=True)
    contract_type = fields.Selection([
        ('service', 'Service Contract'),
        ('amc', 'AMC'),
        ('maintenance', 'Maintenance'),
        ('other', 'Other'),
    ], default='service', tracking=True)
    category = fields.Char()
    department = fields.Char()
    vendor_id = fields.Many2one('vc.vendor', ondelete='set null', tracking=True)
    contractor_id = fields.Many2one('vc.contractor', ondelete='set null', tracking=True)
    site_id = fields.Many2one('vc.site', tracking=True)
    site = fields.Char(string='Site (Legacy)')
    date_start = fields.Date(tracking=True)
    date_end = fields.Date(tracking=True)
    renewal_date = fields.Date()
    notice_period_days = fields.Integer(string='Notice Period (Days)', default=30)
    value = fields.Monetary(currency_field='currency_id')
    tax_amount = fields.Monetary(currency_field='currency_id')
    total_value = fields.Monetary(currency_field='currency_id', compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    payment_frequency = fields.Char()
    payment_terms = fields.Char()
    is_amc = fields.Boolean(string='AMC')
    amc_details = fields.Text()
    has_sla = fields.Boolean(string='SLA')
    sla_response_hours = fields.Float(default=2.0)
    sla_resolution_hours = fields.Float(default=8.0)
    service_frequency = fields.Char()
    manager_id = fields.Many2one('res.users', string='Responsible Manager')
    document_ids = fields.One2many('vc.document', 'contract_id')
    renewal_ids = fields.One2many('vc.contract.renewal', 'contract_id')
    breach_ids = fields.One2many('vc.sla.breach', 'contract_id')
    scope = fields.Text()
    renewal_notes = fields.Text()
    termination_reason = fields.Text()
    approval_date = fields.Date(readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('pending_approval', 'Under Approval'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('expiring', 'Expiring'),
        ('expired', 'Expired'),
        ('renewal_pending', 'Renewal Pending'),
        ('renewed', 'Renewed'),
        ('terminated', 'Terminated'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

    @api.depends('value', 'tax_amount')
    def _compute_total(self):
        for rec in self:
            rec.total_value = (rec.value or 0.0) + (rec.tax_amount or 0.0)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError('Contract end date must be on or after start date.')

    @api.constrains('value', 'tax_amount')
    def _check_amounts(self):
        for rec in self:
            if rec.value is not False and rec.value < 0:
                raise ValidationError('Contract amount cannot be negative.')
            if rec.tax_amount is not False and rec.tax_amount < 0:
                raise ValidationError('Tax amount cannot be negative.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('vc.contract') or 'CON-NEW'
            if vals.get('contract_type') == 'amc':
                vals['is_amc'] = True
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('contract_created', rec, 'Contract created', new_state=rec.state)
        return records

    def write(self, vals):
        if vals.get('contract_type') == 'amc':
            vals['is_amc'] = True
        if vals.get('site_id') and 'site' not in vals:
            vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        return super().write(vals)

    def is_assignable(self):
        self.ensure_one()
        return self.state in ('active', 'expiring', 'renewed')

    def action_submit(self):
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'cancelled'), 'submit')
            if not rec.vendor_id and not rec.contractor_id:
                raise UserError('Select a vendor or contractor.')
            if not rec.date_start or not rec.date_end:
                raise UserError('Start and end dates are required.')
            prev = rec.state
            rec.state = 'submitted'
            self._vc_log('contract_submitted', rec, 'Contract submitted', prev, 'submitted')
        return True

    def action_approve(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('submitted', 'pending_approval', 'approved'), 'approve')
            prev = rec.state
            rec.write({
                'state': 'approved',
                'approval_date': fields.Date.context_today(self),
                'approved_by_id': self.env.user.id,
            })
            self._vc_log('contract_approved', rec, 'Contract approved', prev, 'approved')
        return True

    def action_activate(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        today = fields.Date.context_today(self)
        for rec in self:
            self._vc_assert_transition(rec, ('approved', 'renewed', 'expiring'), 'activate')
            if rec.date_end and rec.date_end < today:
                raise UserError('Cannot activate an expired contract.')
            prev = rec.state
            rec.write({'state': 'active', 'active': True})
            self._vc_log('contract_activated', rec, 'Contract activated', prev, 'active')
        return True

    def action_renew(self, values=None):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        values = values or {}
        for rec in self:
            self._vc_assert_transition(
                rec, ('active', 'expiring', 'expired', 'renewal_pending', 'renewed'), 'renew'
            )
            new_end = values.get('date_end') or rec.date_end
            if values.get('date_end'):
                new_end = fields.Date.to_date(values['date_end'])
            if not new_end or (rec.date_end and new_end <= rec.date_end):
                raise UserError('Renewal end date must be after the current end date.')
            self.env['vc.contract.renewal'].create({
                'contract_id': rec.id,
                'previous_end_date': rec.date_end,
                'new_end_date': new_end,
                'notes': values.get('renewal_notes') or rec.renewal_notes or '',
                'user_id': self.env.user.id,
            })
            prev = rec.state
            write_vals = {
                'date_end': new_end,
                'renewal_date': fields.Date.context_today(self),
                'state': 'renewed',
                'renewal_notes': values.get('renewal_notes') or rec.renewal_notes,
            }
            if values.get('value') is not None:
                write_vals['value'] = values['value']
            if values.get('date_start'):
                write_vals['date_start'] = fields.Date.to_date(values['date_start'])
            rec.write(write_vals)
            self._vc_log('contract_renewed', rec, 'Contract renewed', prev, 'renewed')
        return True

    def action_terminate(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(
                rec, ('active', 'expiring', 'approved', 'renewed', 'renewal_pending'), 'terminate'
            )
            if not rec.termination_reason:
                raise UserError('Please provide a termination reason.')
            prev = rec.state
            rec.state = 'terminated'
            self._vc_log('contract_terminated', rec, rec.termination_reason, prev, 'terminated')
        return True

    def action_cancel(self):
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'submitted', 'pending_approval'), 'cancel')
            prev = rec.state
            rec.state = 'cancelled'
            self._vc_log('contract_cancelled', rec, 'Contract cancelled', prev, 'cancelled')
        return True

    @api.model
    def cron_scan_expiry(self):
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=30)
        active = self.search([('state', 'in', ('active', 'expiring', 'renewed'))])
        for rec in active:
            if not rec.date_end:
                continue
            if rec.date_end < today:
                prev = rec.state
                rec.state = 'expired'
                self._vc_log('contract_expired', rec, 'Contract expired', prev, 'expired')
                self._vc_notify(
                    'Contract expired',
                    '%s expired on %s' % (rec.name, rec.date_end),
                    'contract', rec._name, rec.id, 'critical',
                )
            elif rec.date_end <= soon and rec.state != 'expiring':
                prev = rec.state
                rec.state = 'expiring'
                self._vc_log('contract_expiring', rec, 'Contract expiring soon', prev, 'expiring')
                self._vc_notify(
                    'Contract expiring soon',
                    '%s expires on %s' % (rec.name, rec.date_end),
                    'contract', rec._name, rec.id, 'warning',
                )
        return True

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'party': (self.vendor_id.name or self.contractor_id.name or ''),
            'vendor_id': self.vendor_id.id or False,
            'contractor_id': self.contractor_id.id or False,
            'category': self.category or '',
            'type': self._vc_selection_label(self, 'contract_type'),
            'contract_type': self.contract_type,
            'site': self.site or (self.site_id.name if self.site_id else ''),
            'site_id': self.site_id.id or False,
            'date_start': self._vc_date(self.date_start),
            'date_end': self._vc_date(self.date_end),
            'renewal_date': self._vc_date(self.renewal_date),
            'amc_label': 'AMC Active' if self.is_amc and self.state == 'active' else ('AMC' if self.is_amc else '—'),
            'is_amc': self.is_amc,
            'sla_label': '%sh Response' % int(self.sla_response_hours) if self.has_sla else '—',
            'has_sla': self.has_sla,
            'sla_response_hours': self.sla_response_hours,
            'sla_resolution_hours': self.sla_resolution_hours,
            'state': self.state,
            'state_label': self._vc_selection_label(self, 'state'),
            'value': self.total_value,
            'payment_terms': self.payment_terms or '',
            'amc_details': self.amc_details or '',
        }


class VcContractRenewal(models.Model):
    _name = 'vc.contract.renewal'
    _description = 'Contract Renewal History'
    _order = 'create_date desc'

    name = fields.Char(default='Renewal', required=True)
    contract_id = fields.Many2one('vc.contract', required=True, ondelete='cascade')
    previous_end_date = fields.Date()
    new_end_date = fields.Date(required=True)
    notes = fields.Text()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    renewal_date = fields.Date(default=fields.Date.context_today)


class VcSlaBreach(models.Model):
    _name = 'vc.sla.breach'
    _description = 'SLA Breach'
    _inherit = ['vc.api.mixin']
    _order = 'breach_date desc, id desc'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    contract_id = fields.Many2one('vc.contract', required=True, ondelete='cascade')
    vendor_id = fields.Many2one(related='contract_id.vendor_id', store=True)
    contractor_id = fields.Many2one(related='contract_id.contractor_id', store=True)
    site_id = fields.Many2one('vc.site')
    sla_type = fields.Selection([
        ('response', 'Response Time'),
        ('resolution', 'Resolution Time'),
        ('other', 'Other'),
    ], default='response', required=True)
    expected_hours = fields.Float()
    actual_hours = fields.Float()
    breach_date = fields.Datetime(default=fields.Datetime.now)
    breach_duration = fields.Float(string='Breach Duration (Hours)', compute='_compute_breach_duration', store=True)
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='medium')
    description = fields.Text()
    state = fields.Selection([
        ('open', 'Open'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], default='open', index=True)
    resolution_notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('expected_hours', 'actual_hours')
    def _compute_breach_duration(self):
        for rec in self:
            rec.breach_duration = max((rec.actual_hours or 0.0) - (rec.expected_hours or 0.0), 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vc.sla.breach') or 'SLA-NEW'
        records = super().create(vals_list)
        for rec in records:
            self._vc_notify(
                'SLA breach',
                '%s on %s' % (rec.name, rec.contract_id.display_name),
                'sla', rec._name, rec.id, 'critical',
            )
            self._vc_log('sla_breach', rec, rec.description or 'SLA breach recorded', new_state=rec.state)
        return records
