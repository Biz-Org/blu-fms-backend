# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcDocument(models.Model):
    _name = 'vc.document'
    _description = 'Vendor / Contractor Document'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'expiry_date asc, id desc'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Document ID', copy=False, readonly=True, default='New')
    document_type = fields.Selection([
        ('statutory', 'Statutory'),
        ('insurance', 'Insurance'),
        ('safety', 'Safety'),
        ('license', 'License'),
        ('training', 'Training'),
        ('identity', 'Identity'),
        ('other', 'Other'),
    ], default='other', tracking=True)
    category = fields.Char()
    document_number = fields.Char()
    vendor_id = fields.Many2one('vc.vendor', ondelete='cascade', index=True)
    contractor_id = fields.Many2one('vc.contractor', ondelete='cascade', index=True)
    worker_id = fields.Many2one('vc.worker', ondelete='cascade', index=True)
    contract_id = fields.Many2one('vc.contract', ondelete='set null')
    site_id = fields.Many2one('vc.site')
    site = fields.Char(string='Site (Legacy)')
    issue_date = fields.Date()
    expiry_date = fields.Date(tracking=True)
    submitted_date = fields.Date()
    verified_date = fields.Date()
    verified_by_id = fields.Many2one('res.users', string='Verified By')
    rejection_reason = fields.Text()
    has_expiry = fields.Boolean(default=True)
    required = fields.Boolean(string='Required for Compliance', default=True)
    attachment = fields.Binary(attachment=True)
    attachment_name = fields.Char()
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'vc_document_attachment_rel',
        'document_id',
        'attachment_id',
        string='Attachments',
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_upload', 'Pending Upload'),
        ('submitted', 'Submitted'),
        ('pending_verification', 'Pending Verification'),
        ('under_verification', 'Under Verification'),
        ('verified', 'Verified'),
        ('expiring', 'Expiring'),
        ('expired', 'Expired'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True, index=True)
    description = fields.Text()

    @api.constrains('issue_date', 'expiry_date')
    def _check_dates(self):
        for rec in self:
            if rec.issue_date and rec.expiry_date and rec.expiry_date < rec.issue_date:
                raise ValidationError('Expiry date cannot be before issue date.')

    @api.constrains('vendor_id', 'contractor_id', 'worker_id')
    def _check_owner(self):
        for rec in self:
            if not (rec.vendor_id or rec.contractor_id or rec.worker_id or rec.contract_id):
                raise ValidationError('Document must be linked to a vendor, contractor, worker, or contract.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('vc.document') or 'DOC-NEW'
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('document_uploaded', rec, 'Document created', new_state=rec.state)
        return records

    def write(self, vals):
        if vals.get('site_id') and 'site' not in vals:
            vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        return super().write(vals)

    def action_submit_for_verification(self):
        for rec in self:
            self._vc_assert_transition(
                rec, ('draft', 'pending_upload', 'rejected', 'submitted', 'pending_verification'), 'submit'
            )
            if not rec.attachment and not rec.attachment_ids:
                raise UserError('Please upload a document file before submitting.')
            prev = rec.state
            rec.write({
                'state': 'pending_verification',
                'submitted_date': fields.Date.context_today(self),
            })
            self._vc_log('document_submitted', rec, 'Document submitted for verification', prev, 'pending_verification')
        return True

    def action_verify(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        today = fields.Date.context_today(self)
        for rec in self:
            self._vc_assert_transition(
                rec, ('pending_verification', 'under_verification', 'submitted', 'expiring'), 'verify'
            )
            if rec.has_expiry and rec.expiry_date and rec.expiry_date < today:
                raise UserError('Cannot verify an already expired document.')
            prev = rec.state
            state = 'verified'
            if rec.has_expiry and rec.expiry_date:
                soon = today + timedelta(days=30)
                if rec.expiry_date <= soon:
                    state = 'expiring'
            rec.write({
                'state': state,
                'verified_date': today,
                'verified_by_id': self.env.user.id,
                'rejection_reason': False,
            })
            self._vc_log('document_verified', rec, 'Document verified', prev, state)
        return True

    def action_reject(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(
                rec, ('pending_verification', 'under_verification', 'submitted', 'verified', 'expiring'), 'reject'
            )
            if not rec.rejection_reason:
                raise UserError('Please provide a rejection reason.')
            prev = rec.state
            rec.state = 'rejected'
            self._vc_log('document_rejected', rec, rec.rejection_reason, prev, 'rejected')
        return True

    @api.model
    def cron_scan_expiry(self):
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=30)
        # Mark expired
        expired = self.search([
            ('has_expiry', '=', True),
            ('expiry_date', '<', today),
            ('state', 'not in', ('expired', 'rejected', 'draft')),
        ])
        for doc in expired:
            prev = doc.state
            doc.state = 'expired'
            self._vc_log('document_expired', doc, 'Document expired', prev, 'expired')
            self._vc_notify(
                'Document expired',
                '%s expired on %s' % (doc.name, doc.expiry_date),
                'document', doc._name, doc.id, 'critical',
            )
        # Mark / notify expiring soon
        expiring = self.search([
            ('has_expiry', '=', True),
            ('expiry_date', '>=', today),
            ('expiry_date', '<=', soon),
            ('state', 'in', ('verified', 'expiring', 'pending_verification')),
        ])
        for doc in expiring:
            if doc.state == 'verified':
                doc.state = 'expiring'
            self._vc_notify(
                'Document expiring soon',
                '%s expires on %s' % (doc.name, doc.expiry_date),
                'document', doc._name, doc.id, 'warning',
            )
        return True

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'type': self._vc_selection_label(self, 'document_type'),
            'document_type': self.document_type,
            'vendor_id': self.vendor_id.id or False,
            'contractor_id': self.contractor_id.id or False,
            'worker_id': self.worker_id.id or False,
            'contract_id': self.contract_id.id or False,
            'party': (self.vendor_id.name or self.contractor_id.name or (self.worker_id.name if self.worker_id else '')),
            'site': self.site or (self.site_id.name if self.site_id else ''),
            'issue_date': self._vc_date(self.issue_date),
            'expiry': self._vc_date(self.expiry_date) if self.expiry_date else 'No Expiry',
            'expiry_date': self._vc_date(self.expiry_date),
            'required': self.required,
            'has_attachment': bool(self.attachment or self.attachment_ids),
            'state': self.state,
            'state_label': self._vc_selection_label(self, 'state'),
        }
