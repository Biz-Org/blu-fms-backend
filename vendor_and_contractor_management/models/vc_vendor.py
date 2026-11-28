# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcVendor(models.Model):
    _name = 'vc.vendor'
    _description = 'Vendor'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Vendor ID', copy=False, readonly=True, default='New', tracking=True)
    vendor_type = fields.Selection([
        ('company', 'Company'),
        ('individual', 'Individual'),
        ('agency', 'Agency'),
    ], string='Vendor Type', default='company', tracking=True)
    category = fields.Selection([
        ('electrical', 'Electrical'),
        ('housekeeping', 'Housekeeping'),
        ('security', 'Security'),
        ('hvac', 'HVAC'),
        ('landscaping', 'Landscaping'),
        ('other', 'Other'),
    ], string='Service Category', default='other', tracking=True)
    service_categories = fields.Char(string='Service Categories')
    contact_person = fields.Char(tracking=True)
    designation = fields.Char()
    phone = fields.Char()
    mobile = fields.Char()
    email = fields.Char()
    alternate_phone = fields.Char()
    website = fields.Char()
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', string='Region / State')
    country_id = fields.Many2one('res.country')
    zip = fields.Char()
    address = fields.Text()
    gstin = fields.Char(string='GSTIN', tracking=True)
    pan = fields.Char(string='PAN', tracking=True)
    registration_number = fields.Char()
    company_type = fields.Char()
    years_in_business = fields.Integer()
    registration_date = fields.Date(default=fields.Date.context_today, tracking=True)
    approval_date = fields.Date(readonly=True, tracking=True)
    approved_by_id = fields.Many2one('res.users', readonly=True, tracking=True)
    rejection_reason = fields.Text()
    site_id = fields.Many2one('vc.site', string='Primary Site', tracking=True)
    site = fields.Char(string='Primary Site (Legacy)', help='Kept for compatibility; prefer Site.')
    services = fields.Char(string='Approved Services')
    rating = fields.Float(default=0.0, tracking=True)
    remarks = fields.Text()
    notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_verification', 'Under Verification'),
        ('pending_verification', 'Pending Verification'),  # legacy
        ('pending_approval', 'Pending Approval'),  # legacy
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('rejected', 'Rejected'),
        ('returned', 'Returned'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
        ('blacklisted', 'Blacklisted'),
        ('inactive', 'Inactive'),
    ], default='draft', tracking=True, index=True)
    compliance_state = fields.Selection([
        ('compliant', 'Compliant'),
        ('partial', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('pending', 'Pending Documents'),
    ], default='pending', tracking=True, compute='_compute_compliance_state', store=True)
    document_status = fields.Selection([
        ('missing', 'Missing'),
        ('pending', 'Pending'),
        ('valid', 'Valid'),
        ('expiring', 'Expiring'),
        ('expired', 'Expired'),
    ], compute='_compute_document_status', store=True)
    contract_ids = fields.One2many('vc.contract', 'vendor_id')
    document_ids = fields.One2many('vc.document', 'vendor_id')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('vc_vendor_code_uniq', 'unique(code)', 'Vendor ID must be unique.'),
    ]

    @api.depends('document_ids', 'document_ids.state', 'document_ids.required', 'document_ids.expiry_date')
    def _compute_document_status(self):
        today = fields.Date.context_today(self)
        for vendor in self:
            docs = vendor.document_ids
            if not docs:
                vendor.document_status = 'missing'
                continue
            required = docs.filtered('required')
            if required and any(d.state in ('draft', 'submitted', 'pending_upload', 'pending_verification', 'under_verification', 'rejected') for d in required):
                vendor.document_status = 'pending'
            elif any(d.state == 'expired' or (d.expiry_date and d.expiry_date < today) for d in docs):
                vendor.document_status = 'expired'
            elif any(d.state == 'expiring' for d in docs):
                vendor.document_status = 'expiring'
            else:
                vendor.document_status = 'valid'

    @api.depends('document_ids', 'document_ids.state', 'document_ids.required')
    def _compute_compliance_state(self):
        for vendor in self:
            required = vendor.document_ids.filtered('required')
            if not required:
                vendor.compliance_state = 'pending'
                continue
            verified = required.filtered(lambda d: d.state in ('verified', 'expiring'))
            if len(verified) == len(required):
                vendor.compliance_state = 'compliant'
            elif verified:
                vendor.compliance_state = 'partial'
            elif any(d.state in ('expired', 'rejected') for d in required):
                vendor.compliance_state = 'non_compliant'
            else:
                vendor.compliance_state = 'pending'

    @api.constrains('gstin')
    def _check_gstin(self):
        for rec in self:
            self._vc_validate_gstin(rec.gstin)

    @api.constrains('pan')
    def _check_pan(self):
        for rec in self:
            self._vc_validate_pan(rec.pan)

    @api.constrains('gstin', 'pan', 'company_id')
    def _check_duplicates(self):
        for rec in self:
            if rec.gstin:
                dup = self.search([
                    ('id', '!=', rec.id),
                    ('gstin', '=', rec.gstin.strip().upper()),
                    ('company_id', '=', rec.company_id.id),
                ], limit=1)
                if dup:
                    raise ValidationError('A vendor with GSTIN %s already exists (%s).' % (rec.gstin, dup.code))
            if rec.pan:
                dup = self.search([
                    ('id', '!=', rec.id),
                    ('pan', '=', rec.pan.strip().upper()),
                    ('company_id', '=', rec.company_id.id),
                ], limit=1)
                if dup:
                    raise ValidationError('A vendor with PAN %s already exists (%s).' % (rec.pan, dup.code))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('vc.vendor') or 'VND-NEW'
            if vals.get('gstin'):
                vals['gstin'] = vals['gstin'].strip().upper()
            if vals.get('pan'):
                vals['pan'] = vals['pan'].strip().upper()
            if vals.get('site_id') and not vals.get('site'):
                site = self.env['vc.site'].browse(vals['site_id'])
                vals['site'] = site.name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('vendor_created', rec, 'Vendor created', new_state=rec.state)
        return records

    def write(self, vals):
        if vals.get('gstin'):
            vals['gstin'] = vals['gstin'].strip().upper()
        if vals.get('pan'):
            vals['pan'] = vals['pan'].strip().upper()
        if vals.get('site_id') and 'site' not in vals:
            vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        return super().write(vals)

    def _mandatory_docs_ok(self):
        self.ensure_one()
        required = self.document_ids.filtered('required')
        if not required:
            return False
        today = fields.Date.context_today(self)
        for doc in required:
            if doc.state not in ('verified', 'expiring'):
                return False
            if doc.expiry_date and doc.expiry_date < today:
                return False
        return True

    def action_submit(self):
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'returned', 'rejected'), 'submit')
            if not rec.name or not rec.contact_person:
                raise UserError('Vendor name and contact person are required before submit.')
            prev = rec.state
            rec.state = 'submitted'
            self._vc_log('vendor_submitted', rec, 'Vendor submitted', prev, rec.state)
            self._vc_notify('Vendor pending verification', '%s submitted for verification' % rec.name, 'vendor', rec._name, rec.id, 'info')
        return True

    def action_verify(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('submitted', 'pending_verification', 'under_verification', 'pending_approval'), 'verify')
            prev = rec.state
            rec.state = 'under_verification'
            self._vc_log('vendor_verified', rec, 'Vendor under verification', prev, rec.state)
        return True

    def action_approve(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('under_verification', 'submitted', 'pending_approval', 'pending_verification', 'approved'), 'approve')
            prev = rec.state
            rec.write({
                'state': 'approved',
                'approval_date': fields.Date.context_today(self),
                'approved_by_id': self.env.user.id,
                'rejection_reason': False,
            })
            self._vc_log('vendor_approved', rec, 'Vendor approved', prev, 'approved')
        return True

    def action_reject(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('submitted', 'under_verification', 'pending_verification', 'pending_approval', 'approved'), 'reject')
            if not rec.rejection_reason:
                raise UserError('Please provide a rejection reason.')
            prev = rec.state
            rec.state = 'rejected'
            self._vc_log('vendor_rejected', rec, rec.rejection_reason, prev, 'rejected')
        return True

    def action_activate(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('approved', 'suspended', 'inactive'), 'activate')
            if not rec._mandatory_docs_ok():
                raise UserError('Cannot activate vendor %s: mandatory documents are missing or invalid.' % rec.display_name)
            prev = rec.state
            rec.write({'state': 'active', 'active': True})
            self._vc_log('vendor_activated', rec, 'Vendor activated', prev, 'active')
        return True

    def action_suspend(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('active', 'approved'), 'suspend')
            prev = rec.state
            rec.state = 'suspended'
            self._vc_log('vendor_suspended', rec, 'Vendor suspended', prev, 'suspended')
            self._vc_notify('Vendor suspended', '%s was suspended' % rec.name, 'vendor', rec._name, rec.id, 'warning')
        return True

    def action_reactivate(self):
        return self.action_activate()

    def is_operational(self):
        self.ensure_one()
        return self.active and self.state == 'active'
