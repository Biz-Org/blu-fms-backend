# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcDailyPass(models.Model):
    _name = 'vc.daily.pass'
    _description = 'Daily Pass'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'validity_date desc, id desc'

    name = fields.Char(string='Pass Number', copy=False, readonly=True, default='New')
    pass_type = fields.Selection([
        ('temporary', 'Temporary'),
        ('visitor', 'Visitor'),
        ('emergency', 'Emergency'),
    ], default='temporary', tracking=True)
    visitor_name = fields.Char()
    worker_id = fields.Many2one('vc.worker', ondelete='set null')
    worker_name = fields.Char()
    company = fields.Char(string='Visitor Company')
    phone = fields.Char()
    email = fields.Char()
    contractor_id = fields.Many2one('vc.contractor', ondelete='set null')
    vendor_id = fields.Many2one('vc.vendor', ondelete='set null')
    host_id = fields.Many2one('res.users', string='Host')
    site_id = fields.Many2one('vc.site')
    site = fields.Char(string='Site (Legacy)', required=True)
    purpose = fields.Char()
    priority = fields.Selection([
        ('standard', 'Standard'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='standard')
    valid_from = fields.Datetime()
    valid_until = fields.Datetime()
    validity_date = fields.Date(default=fields.Date.context_today)
    id_type = fields.Char()
    id_reference = fields.Char(groups='vendor_and_contractor_management.group_vc_manager')
    entry_time = fields.Char()
    exit_time = fields.Char()
    approved_by_id = fields.Many2one('res.users', readonly=True)
    approval_datetime = fields.Datetime(readonly=True)
    rejection_reason = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('requested', 'Requested'),  # legacy
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    @api.constrains('valid_from', 'valid_until', 'validity_date')
    def _check_dates(self):
        for rec in self:
            if rec.valid_from and rec.valid_until and rec.valid_until < rec.valid_from:
                raise ValidationError('Valid until must be after valid from.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vc.daily.pass') or 'PASS-NEW'
            if not vals.get('visitor_name') and vals.get('worker_name'):
                vals['visitor_name'] = vals['worker_name']
            if not vals.get('worker_name') and vals.get('visitor_name'):
                vals['worker_name'] = vals['visitor_name']
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('daily_pass_created', rec, 'Daily pass created', new_state=rec.state)
        return records

    def action_submit(self):
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'rejected'), 'submit')
            if not (rec.visitor_name or rec.worker_name or rec.worker_id):
                raise UserError('Visitor/worker name is required.')
            if not rec.site and not rec.site_id:
                raise UserError('Site is required.')
            prev = rec.state
            rec.state = 'submitted'
            self._vc_log('daily_pass_submitted', rec, 'Daily pass submitted', prev, 'submitted')
        return True

    def action_approve(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'submitted', 'requested', 'approved'), 'approve')
            # Duplicate active pass check
            name = rec.visitor_name or rec.worker_name
            if name:
                dup = self.search([
                    ('id', '!=', rec.id),
                    ('state', '=', 'active'),
                    ('site', '=', rec.site),
                    '|', ('visitor_name', '=', name), ('worker_name', '=', name),
                ], limit=1)
                if dup:
                    raise UserError('An active pass already exists for this visitor at this site.')
            prev = rec.state
            rec.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approval_datetime': fields.Datetime.now(),
                'rejection_reason': False,
            })
            self._vc_log('daily_pass_approved', rec, 'Daily pass approved', prev, 'approved')
        return True

    def action_activate(self):
        for rec in self:
            self._vc_assert_transition(rec, ('approved',), 'activate')
            today = fields.Date.context_today(self)
            if rec.validity_date and rec.validity_date < today:
                raise UserError('Cannot activate an expired pass.')
            prev = rec.state
            rec.state = 'active'
            self._vc_log('daily_pass_activated', rec, 'Daily pass activated', prev, 'active')
        return True

    def action_reject(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'submitted', 'requested', 'approved'), 'reject')
            if not rec.rejection_reason:
                raise UserError('Provide a rejection reason.')
            prev = rec.state
            rec.state = 'rejected'
            self._vc_log('daily_pass_rejected', rec, rec.rejection_reason, prev, 'rejected')
        return True

    def action_cancel(self):
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'submitted', 'requested', 'approved', 'active'), 'cancel')
            prev = rec.state
            rec.state = 'cancelled'
            self._vc_log('daily_pass_cancelled', rec, rec.rejection_reason or 'Cancelled', prev, 'cancelled')
        return True

    @api.model
    def cron_scan_expiry(self):
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        to_expire = self.search([
            ('state', 'in', ('active', 'approved')),
            '|',
            ('validity_date', '<', today),
            '&', ('valid_until', '!=', False), ('valid_until', '<', now),
        ])
        for rec in to_expire:
            prev = rec.state
            rec.state = 'expired'
            self._vc_log('daily_pass_expired', rec, 'Daily pass expired', prev, 'expired')
            self._vc_notify(
                'Daily pass expired',
                '%s expired' % rec.name,
                'pass', rec._name, rec.id, 'warning',
            )
        # Expiring today alerts
        expiring = self.search([
            ('state', '=', 'active'),
            ('validity_date', '=', today),
        ])
        for rec in expiring:
            self._vc_notify(
                'Daily pass expiring',
                '%s expires today' % rec.name,
                'pass', rec._name, rec.id, 'info',
            )
        return True

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.name,
            'worker': self.visitor_name or self.worker_name or (self.worker_id.name if self.worker_id else ''),
            'company': self.company or (self.contractor_id.name if self.contractor_id else '') or (self.vendor_id.name if self.vendor_id else ''),
            'site': self.site or (self.site_id.name if self.site_id else ''),
            'purpose': self.purpose or '',
            'validity': self._vc_date(self.validity_date),
            'pass_type': self._vc_selection_label(self, 'pass_type'),
            'state': self.state,
            'state_label': self._vc_selection_label(self, 'state'),
            'phone': self.phone or '',
            'host': self.host_id.name if self.host_id else '',
        }
