# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class VcAttendance(models.Model):
    _name = 'vc.attendance'
    _description = 'Contractor Attendance & Access'
    _inherit = ['vc.api.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Attendance Reference', copy=False, readonly=True, default='New')
    worker_id = fields.Many2one('vc.worker', required=True, ondelete='cascade', index=True)
    contractor_id = fields.Many2one(related='worker_id.contractor_id', store=True)
    vendor_id = fields.Many2one(related='worker_id.vendor_id', store=True)
    site_id = fields.Many2one('vc.site')
    site = fields.Char(string='Site (Legacy)')
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    check_in_dt = fields.Datetime(string='Check-in')
    check_out_dt = fields.Datetime(string='Check-out')
    check_in = fields.Char(help='Legacy display time')
    check_out = fields.Char(help='Legacy display time')
    duration_hours = fields.Float(compute='_compute_duration', store=True)
    entry_gate = fields.Char()
    exit_gate = fields.Char()
    security_user_id = fields.Many2one('res.users', string='Security User')
    rejection_reason = fields.Char()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent', 'Absent'),
        ('on_leave', 'On Leave'),
        ('denied', 'Access Denied'),
        ('checked_out', 'Checked Out'),
    ], default='scheduled', index=True)
    access_state = fields.Selection([
        ('active', 'Access Active'),
        ('expired', 'Access Expired'),
        ('suspended', 'Access Suspended'),
        ('denied', 'Denied'),
    ], default='active')
    notes = fields.Char()

    @api.depends('check_in_dt', 'check_out_dt')
    def _compute_duration(self):
        for rec in self:
            if rec.check_in_dt and rec.check_out_dt:
                delta = rec.check_out_dt - rec.check_in_dt
                rec.duration_hours = delta.total_seconds() / 3600.0
            else:
                rec.duration_hours = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vc.attendance') or 'ATT-NEW'
            if vals.get('site_id') and not vals.get('site'):
                vals['site'] = self.env['vc.site'].browse(vals['site_id']).name
        return super().create(vals_list)

    def _fmt_time(self, dt):
        if not dt:
            return ''
        return fields.Datetime.context_timestamp(self, dt).strftime('%H:%M')

    def action_check_in(self):
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        for rec in self:
            worker = rec.worker_id
            site_id = rec.site_id.id if rec.site_id else False
            ok, reason = worker.is_eligible_for_access(site_id=site_id)
            if not ok:
                raise UserError(reason)
            if rec.date and rec.date > today:
                raise UserError('Attendance for future dates is not allowed.')
            open_att = self.search([
                ('worker_id', '=', worker.id),
                ('state', 'in', ('present', 'late')),
                ('check_out_dt', '=', False),
                ('id', '!=', rec.id),
            ], limit=1)
            if open_att:
                raise UserError('Worker already has an active check-in (%s).' % open_att.name)
            rec.write({
                'check_in_dt': now,
                'check_in': self._fmt_time(now),
                'state': 'present',
                'access_state': 'active',
                'security_user_id': self.env.user.id,
                'rejection_reason': False,
            })
            self._vc_log('attendance_check_in', rec, 'Check-in', new_state='present', site_id=rec.site_id)
        return True

    def action_check_out(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state not in ('present', 'late') or not rec.check_in_dt:
                raise UserError('No active check-in found for checkout.')
            if rec.check_out_dt:
                raise UserError('Already checked out.')
            rec.write({
                'check_out_dt': now,
                'check_out': self._fmt_time(now),
                'state': 'checked_out',
            })
            self._vc_log('attendance_check_out', rec, 'Check-out', previous_state='present', new_state='checked_out')
        return True

    def action_deny_access(self):
        for rec in self:
            if not rec.rejection_reason:
                raise UserError('Provide a rejection reason to deny access.')
            rec.write({
                'state': 'denied',
                'access_state': 'denied',
            })
            self._vc_log('attendance_denied', rec, rec.rejection_reason, new_state='denied')
        return True

    @api.model
    def check_in_worker(self, worker_id, site_id=False, values=None):
        values = values or {}
        worker = self.env['vc.worker'].browse(worker_id)
        if not worker.exists():
            raise UserError('Worker not found.')
        ok, reason = worker.is_eligible_for_access(site_id=site_id or False)
        if not ok:
            raise UserError(reason)
        open_att = self.search([
            ('worker_id', '=', worker.id),
            ('state', 'in', ('present', 'late')),
            ('check_out_dt', '=', False),
        ], limit=1)
        if open_att:
            raise UserError('Worker already has an active check-in.')
        now = fields.Datetime.now()
        att = self.create({
            'worker_id': worker.id,
            'site_id': site_id or worker.site_id.id or False,
            'site': values.get('site') or (worker.site_id.name if worker.site_id else worker.site),
            'date': fields.Date.context_today(self),
            'check_in_dt': now,
            'check_in': fields.Datetime.context_timestamp(self, now).strftime('%H:%M'),
            'entry_gate': values.get('entry_gate'),
            'state': 'present',
            'access_state': 'active',
            'security_user_id': self.env.user.id,
            'notes': values.get('notes'),
        })
        self._vc_log('attendance_check_in', att, 'Check-in', new_state='present', site_id=att.site_id)
        return att

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.name,
            'worker_id': self.worker_id.id,
            'worker_code': self.worker_id.code,
            'worker_name': self.worker_id.name,
            'contractor': self.contractor_id.name or '',
            'vendor': self.vendor_id.name or '',
            'site': self.site or (self.site_id.name if self.site_id else ''),
            'date': self._vc_date(self.date),
            'check_in': self.check_in or (self._vc_datetime(self.check_in_dt) if self.check_in_dt else '—'),
            'check_out': self.check_out or (self._vc_datetime(self.check_out_dt) if self.check_out_dt else '—'),
            'duration_hours': self.duration_hours,
            'state': self.state,
            'state_label': self._vc_selection_label(self, 'state'),
            'access_state': self.access_state,
        }
