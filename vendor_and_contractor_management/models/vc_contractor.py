# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcContractor(models.Model):
    _name = 'vc.contractor'
    _description = 'Contractor'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Contractor ID', copy=False, readonly=True, default='New', tracking=True)
    vendor_id = fields.Many2one('vc.vendor', string='Linked Vendor', tracking=True)
    contractor_type = fields.Selection([
        ('civil', 'Civil'),
        ('electrical', 'Electrical'),
        ('mechanical', 'Mechanical'),
        ('security', 'Security'),
        ('facility', 'Facility'),
        ('other', 'Other'),
    ], default='other', tracking=True, string='Contractor Category')
    work_category = fields.Char(string='Work Category')
    specialization = fields.Char(string='Specialization')
    contact_person = fields.Char(tracking=True)
    phone = fields.Char()
    email = fields.Char()
    address = fields.Text()
    site_id = fields.Many2one('vc.site', string='Site', tracking=True)
    site = fields.Char(string='Site (Legacy)')
    contract_id = fields.Many2one('vc.contract')
    registration_details = fields.Text()
    verification_checklist = fields.Text()
    verification_complete = fields.Boolean(default=False, tracking=True)
    approval_date = fields.Date(readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True)
    rejection_reason = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('pending', 'Pending'),  # legacy
        ('under_verification', 'Under Verification'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ], default='draft', tracking=True, index=True)
    compliance_state = fields.Selection([
        ('compliant', 'Compliant'),
        ('partial', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('pending', 'Pending'),
    ], default='pending', compute='_compute_compliance_state', store=True)
    worker_ids = fields.One2many('vc.worker', 'contractor_id')
    document_ids = fields.One2many('vc.document', 'contractor_id')
    remarks = fields.Text()
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('vc_contractor_code_uniq', 'unique(code)', 'Contractor ID must be unique.'),
    ]

    @api.depends('document_ids', 'document_ids.state', 'document_ids.required')
    def _compute_compliance_state(self):
        for rec in self:
            required = rec.document_ids.filtered('required')
            if not required:
                rec.compliance_state = 'pending'
                continue
            verified = required.filtered(lambda d: d.state in ('verified', 'expiring'))
            if len(verified) == len(required):
                rec.compliance_state = 'compliant'
            elif verified:
                rec.compliance_state = 'partial'
            elif any(d.state in ('expired', 'rejected') for d in required):
                rec.compliance_state = 'non_compliant'
            else:
                rec.compliance_state = 'pending'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('vc.contractor') or 'CTR-NEW'
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('contractor_created', rec, 'Contractor created', new_state=rec.state)
        return records

    def write(self, vals):
        if vals.get('site_id') and 'site' not in vals:
            vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        return super().write(vals)

    def _verification_ok(self):
        self.ensure_one()
        if not self.verification_complete:
            return False
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
            self._vc_assert_transition(rec, ('draft', 'rejected', 'pending'), 'submit')
            if not rec.name or not rec.contact_person:
                raise UserError('Contractor name and contact person are required.')
            prev = rec.state
            rec.state = 'submitted'
            self._vc_log('contractor_submitted', rec, 'Contractor submitted', prev, 'submitted')
            self._vc_notify('Contractor pending verification', '%s submitted' % rec.name, 'contractor', rec._name, rec.id)
        return True

    def action_start_verification(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('submitted', 'pending', 'under_verification'), 'start verification')
            prev = rec.state
            rec.state = 'under_verification'
            self._vc_log('contractor_verification', rec, 'Verification started', prev, 'under_verification')
        return True

    def action_approve(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('under_verification', 'submitted', 'pending', 'approved'), 'approve')
            prev = rec.state
            rec.write({
                'state': 'approved',
                'approval_date': fields.Date.context_today(self),
                'approved_by_id': self.env.user.id,
                'rejection_reason': False,
            })
            self._vc_log('contractor_approved', rec, 'Contractor approved', prev, 'approved')
        return True

    def action_reject(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('submitted', 'under_verification', 'pending', 'approved'), 'reject')
            if not rec.rejection_reason:
                raise UserError('Please provide a rejection reason.')
            prev = rec.state
            rec.state = 'rejected'
            self._vc_log('contractor_rejected', rec, rec.rejection_reason, prev, 'rejected')
        return True

    def action_activate(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('approved', 'suspended', 'inactive'), 'activate')
            if not rec._verification_ok():
                raise UserError(
                    'Cannot activate contractor %s: complete verification checklist and mandatory documents.'
                    % rec.display_name
                )
            if rec.vendor_id and not rec.vendor_id.is_operational():
                raise UserError('Linked vendor must be active before activating the contractor.')
            prev = rec.state
            rec.write({'state': 'active', 'active': True})
            self._vc_log('contractor_activated', rec, 'Contractor activated', prev, 'active')
        return True

    def action_suspend(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('active', 'approved'), 'suspend')
            prev = rec.state
            rec.state = 'suspended'
            self._vc_log('contractor_suspended', rec, 'Contractor suspended', prev, 'suspended')
            self._vc_notify('Contractor suspended', '%s was suspended' % rec.name, 'contractor', rec._name, rec.id, 'warning')
        return True

    def action_reactivate(self):
        return self.action_activate()

    def is_operational(self):
        self.ensure_one()
        return self.active and self.state == 'active'

    def can_assign_workers(self):
        self.ensure_one()
        return self.is_operational()
