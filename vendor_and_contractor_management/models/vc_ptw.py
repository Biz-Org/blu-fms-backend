# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcPermitToWork(models.Model):
    _name = 'vc.ptw'
    _description = 'Permit to Work'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'validity_date desc, id desc'

    name = fields.Char(string='Permit Number', copy=False, readonly=True, default='New')
    title = fields.Char()
    permit_type = fields.Selection([
        ('hot_work', 'Hot Work'),
        ('cold_work', 'Cold Work'),
        ('electrical', 'Electrical'),
        ('height', 'Height Work'),
        ('confined', 'Confined Space'),
        ('excavation', 'Excavation'),
        ('general', 'General Work'),
        ('other', 'Other'),
    ], default='general', tracking=True)
    work_activity = fields.Char(required=True)
    work_description = fields.Text()
    vendor_id = fields.Many2one('vc.vendor', ondelete='set null')
    contractor_id = fields.Many2one('vc.contractor', ondelete='set null', tracking=True)
    worker_ids = fields.Many2many('vc.worker', string='Workers')
    site_id = fields.Many2one('vc.site')
    site = fields.Char(string='Site (Legacy)')
    location = fields.Char(string='Work Area')
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='medium', tracking=True)
    priority = fields.Selection([
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], default='normal')
    date_start = fields.Datetime(string='Start Datetime')
    date_end = fields.Datetime(string='End Datetime')
    validity_date = fields.Date(default=fields.Date.context_today)
    work_datetime = fields.Datetime()
    safety_checklist = fields.Text()
    safety_checklist_done = fields.Boolean(default=False)
    ppe_required = fields.Char()
    ppe_checklist = fields.Text()
    ppe_compliant = fields.Boolean(default=False)
    isolation_requirements = fields.Text()
    emergency_precautions = fields.Text()
    safety_officer_id = fields.Many2one('res.users', string='Safety Officer')
    issued_by_id = fields.Many2one('res.users', string='Issued By', readonly=True)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True)
    approval_datetime = fields.Datetime(readonly=True)
    closure_details = fields.Text()
    closed_by_id = fields.Many2one('res.users', readonly=True)
    closed_datetime = fields.Datetime(readonly=True)
    rejection_reason = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    remarks = fields.Text()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('pending_safety', 'Safety Verification'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('issued', 'Issued'),
        ('active', 'In Progress'),
        ('closed', 'Closed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], default='draft', tracking=True, index=True)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError('End datetime must be after start datetime.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vc.ptw') or 'PTW-NEW'
            if not vals.get('title') and vals.get('work_activity'):
                vals['title'] = vals['work_activity']
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('ptw_created', rec, 'PTW created', new_state=rec.state)
        return records

    def action_submit(self):
        for rec in self:
            self._vc_assert_transition(rec, ('draft', 'rejected'), 'submit')
            if not rec.contractor_id and not rec.vendor_id:
                raise UserError('Contractor or vendor is required.')
            if rec.contractor_id and not rec.contractor_id.is_operational():
                raise UserError('Contractor must be active.')
            if not rec.safety_checklist and not rec.safety_checklist_done:
                raise UserError('Safety checklist is required.')
            prev = rec.state
            rec.state = 'submitted'
            self._vc_log('ptw_submitted', rec, 'PTW submitted', prev, 'submitted')
            self._vc_notify('PTW pending approval', '%s submitted' % rec.name, 'ptw', rec._name, rec.id)
        return True

    def action_safety_verify(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('submitted', 'pending_safety'), 'safety verify')
            if not rec.ppe_compliant and not rec.ppe_checklist:
                raise UserError('PPE compliance/checklist is required.')
            prev = rec.state
            rec.write({
                'state': 'pending_approval',
                'safety_officer_id': self.env.user.id,
                'safety_checklist_done': True,
            })
            self._vc_log('ptw_safety_verified', rec, 'Safety verified', prev, 'pending_approval')
        return True

    def action_approve(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(rec, ('pending_approval', 'pending_safety', 'submitted', 'approved'), 'approve')
            prev = rec.state
            rec.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approval_datetime': fields.Datetime.now(),
                'rejection_reason': False,
            })
            self._vc_log('ptw_approved', rec, 'PTW approved', prev, 'approved')
        return True

    def action_issue(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_supervisor')
        for rec in self:
            self._vc_assert_transition(rec, ('approved',), 'issue')
            prev = rec.state
            rec.write({
                'state': 'issued',
                'issued_by_id': self.env.user.id,
            })
            self._vc_log('ptw_issued', rec, 'PTW issued', prev, 'issued')
        return True

    def action_start_work(self):
        now = fields.Datetime.now()
        for rec in self:
            self._vc_assert_transition(rec, ('issued', 'active'), 'start work')
            if rec.date_end and now > rec.date_end:
                raise UserError('Permit has expired; work cannot start.')
            if rec.validity_date and rec.validity_date < fields.Date.context_today(self):
                raise UserError('Permit validity date has passed.')
            prev = rec.state
            rec.state = 'active'
            self._vc_log('ptw_started', rec, 'Work started', prev, 'active')
        return True

    def action_close(self):
        for rec in self:
            self._vc_assert_transition(rec, ('issued', 'active'), 'close')
            if rec.state == 'closed':
                raise UserError('Permit is already closed.')
            prev = rec.state
            rec.write({
                'state': 'closed',
                'closed_by_id': self.env.user.id,
                'closed_datetime': fields.Datetime.now(),
                'closure_details': rec.closure_details or 'Closed',
            })
            self._vc_log('ptw_closed', rec, rec.closure_details or 'Closed', prev, 'closed')
        return True

    def action_reject(self):
        self._vc_require_group('vendor_and_contractor_management.group_vc_manager')
        for rec in self:
            self._vc_assert_transition(
                rec, ('draft', 'submitted', 'pending_safety', 'pending_approval', 'approved'), 'reject'
            )
            if not rec.rejection_reason:
                raise UserError('Provide a rejection reason.')
            prev = rec.state
            rec.state = 'rejected'
            self._vc_log('ptw_rejected', rec, rec.rejection_reason, prev, 'rejected')
        return True

    def action_cancel(self):
        for rec in self:
            self._vc_assert_transition(
                rec, ('draft', 'submitted', 'pending_safety', 'pending_approval', 'approved', 'issued'), 'cancel'
            )
            prev = rec.state
            rec.state = 'cancelled'
            self._vc_log('ptw_cancelled', rec, 'Cancelled', prev, 'cancelled')
        return True

    @api.model
    def cron_scan_expiry(self):
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        open_states = ('approved', 'issued', 'active', 'pending_approval', 'pending_safety')
        records = self.search([('state', 'in', open_states)])
        for rec in records:
            expired = False
            if rec.date_end and rec.date_end < now:
                expired = True
            elif rec.validity_date and rec.validity_date < today:
                expired = True
            if expired:
                prev = rec.state
                rec.state = 'expired'
                self._vc_log('ptw_expired', rec, 'PTW expired', prev, 'expired')
                self._vc_notify('PTW expired', '%s expired' % rec.name, 'ptw', rec._name, rec.id, 'warning')
            elif rec.state in ('submitted', 'pending_safety', 'pending_approval'):
                self._vc_notify(
                    'PTW pending approval',
                    '%s awaiting action' % rec.name,
                    'ptw', rec._name, rec.id, 'info',
                )
        return True

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.name,
            'title': self.title or self.work_activity,
            'activity': self.work_activity,
            'party': (self.vendor_id.name or self.contractor_id.name or ''),
            'site': self.site or (self.site_id.name if self.site_id else ''),
            'location': self.location or '',
            'risk': self.risk_level,
            'risk_label': self._vc_selection_label(self, 'risk_level'),
            'permit_type': self.permit_type,
            'permit_type_label': self._vc_selection_label(self, 'permit_type'),
            'validity': self._vc_date(self.validity_date),
            'date_start': self._vc_datetime(self.date_start),
            'date_end': self._vc_datetime(self.date_end),
            'state': self.state,
            'state_label': self._vc_selection_label(self, 'state'),
            'workers': [{'id': w.id, 'name': w.name} for w in self.worker_ids],
        }
