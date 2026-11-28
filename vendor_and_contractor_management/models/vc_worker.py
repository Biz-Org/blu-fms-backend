# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcWorker(models.Model):
    _name = 'vc.worker'
    _description = 'Contractor Worker'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Worker ID', copy=False, readonly=True, default='New', tracking=True)
    image_1920 = fields.Image(string='Photo', max_width=1920, max_height=1920)
    contractor_id = fields.Many2one('vc.contractor', required=True, ondelete='cascade', tracking=True)
    vendor_id = fields.Many2one(
        'vc.vendor', related='contractor_id.vendor_id', store=True, readonly=True
    )
    worker_category = fields.Char()
    skill = fields.Char(string='Skill / Trade')
    skills = fields.Char()
    role = fields.Char(string='Job Designation')
    phone = fields.Char()
    email = fields.Char()
    emergency_contact = fields.Char()
    site_id = fields.Many2one('vc.site', string='Site', tracking=True)
    site = fields.Char(string='Site (Legacy)')
    supervisor = fields.Char()
    supervisor_id = fields.Many2one('res.users', string='Supervisor User')
    joining_date = fields.Date(default=fields.Date.context_today)
    id_number = fields.Char(string='ID Number', groups='vendor_and_contractor_management.group_vc_manager')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired'),
    ], default='draft', tracking=True, index=True)
    document_status = fields.Selection([
        ('valid', 'Valid'),
        ('expiring', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('missing', 'Missing'),
        ('pending', 'Pending'),
    ], default='missing', compute='_compute_document_status', store=True)
    compliance_state = fields.Selection([
        ('compliant', 'Compliant'),
        ('partial', 'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('pending', 'Pending'),
    ], default='pending', compute='_compute_compliance_state', store=True)
    document_ids = fields.One2many('vc.document', 'worker_id')
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ('vc_worker_code_uniq', 'unique(code)', 'Worker ID must be unique.'),
    ]

    @api.depends('document_ids', 'document_ids.state', 'document_ids.required', 'document_ids.expiry_date')
    def _compute_document_status(self):
        today = fields.Date.context_today(self)
        for worker in self:
            docs = worker.document_ids
            if not docs:
                worker.document_status = 'missing'
                continue
            required = docs.filtered('required')
            check = required or docs
            if any(d.state == 'expired' or (d.expiry_date and d.expiry_date < today) for d in check):
                worker.document_status = 'expired'
            elif any(d.state == 'expiring' for d in check):
                worker.document_status = 'expiring'
            elif required and any(d.state not in ('verified', 'expiring') for d in required):
                worker.document_status = 'pending'
            elif required and all(d.state in ('verified', 'expiring') for d in required):
                worker.document_status = 'valid'
            else:
                worker.document_status = 'pending'

    @api.depends('document_ids', 'document_ids.state', 'document_ids.required')
    def _compute_compliance_state(self):
        for worker in self:
            required = worker.document_ids.filtered('required')
            if not required:
                worker.compliance_state = 'pending'
                continue
            verified = required.filtered(lambda d: d.state in ('verified', 'expiring'))
            if len(verified) == len(required):
                worker.compliance_state = 'compliant'
            elif verified:
                worker.compliance_state = 'partial'
            else:
                worker.compliance_state = 'non_compliant' if any(
                    d.state in ('expired', 'rejected') for d in required
                ) else 'pending'

    @api.constrains('name', 'contractor_id')
    def _check_duplicate_worker(self):
        for rec in self:
            if self.search_count([
                ('id', '!=', rec.id),
                ('contractor_id', '=', rec.contractor_id.id),
                ('name', '=ilike', rec.name),
            ]):
                raise ValidationError('A worker with the same name already exists for this contractor.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('vc.worker') or 'W-NEW'
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('worker_created', rec, 'Worker created', new_state=rec.state)
        return records

    def write(self, vals):
        if vals.get('site_id') and 'site' not in vals:
            vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        return super().write(vals)

    def _docs_ok(self):
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
            self._vc_assert_transition(rec, ('draft', 'pending', 'inactive'), 'submit')
            if not rec.contractor_id.can_assign_workers():
                raise UserError('Contractor must be approved and active to submit workers.')
            prev = rec.state
            rec.state = 'submitted'
            self._vc_log('worker_submitted', rec, 'Worker submitted', prev, 'submitted')
        return True

    def action_activate(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'pending', 'submitted', 'suspended', 'inactive', 'on_leave'), 'activate')
            if not rec.contractor_id.can_assign_workers():
                raise UserError('Cannot activate worker: contractor is not operational.')
            if not rec._docs_ok():
                raise UserError('Cannot activate worker %s: mandatory documents are missing or invalid.' % rec.display_name)
            if not rec.site_id and not rec.site:
                raise UserError('Site assignment is required to activate a worker.')
            prev = rec.state
            rec.write({'state': 'active', 'active': True})
            self._vc_log('worker_activated', rec, 'Worker activated', prev, 'active')
        return True

    def action_suspend(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('active', 'on_leave'), 'suspend')
            prev = rec.state
            rec.state = 'suspended'
            self._vc_log('worker_suspended', rec, 'Worker suspended', prev, 'suspended')
        return True

    def action_reactivate(self):
        return self.action_activate()

    def is_eligible_for_access(self, site_id=False):
        self.ensure_one()
        if not self.active or self.state != 'active':
            return False, 'Worker is not active.'
        if not self.contractor_id.is_operational():
            return False, 'Contractor is not approved/active.'
        vendor = self.vendor_id
        if vendor and not vendor.is_operational():
            return False, 'Vendor is not approved/active.'
        if not self._docs_ok():
            return False, 'Mandatory documents missing or expired.'
        if site_id:
            if self.site_id and self.site_id.id != site_id:
                return False, 'Worker is not assigned to this site.'
        return True, ''
