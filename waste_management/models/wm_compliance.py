# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmCompliance(models.Model):
    _name = 'wm.compliance'
    _description = 'Waste Compliance'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'expiry_date asc, id desc'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    title = fields.Char(required=True, tracking=True)
    category = fields.Selection([
        ('license', 'License'),
        ('permit', 'Permit'),
        ('certificate', 'Certificate'),
        ('regulation', 'Regulation'),
        ('audit', 'Audit Requirement'),
        ('other', 'Other'),
    ], default='permit', required=True)
    waste_category = fields.Selection([
        ('dry', 'Dry'),
        ('wet', 'Wet'),
        ('hazardous', 'Hazardous'),
        ('recyclable', 'Recyclable'),
        ('ewaste', 'E-Waste'),
        ('biomedical', 'Biomedical'),
        ('general', 'General'),
    ])
    regulation = fields.Char(string='Applicable Regulation')
    entry_id = fields.Many2one('wm.entry', ondelete='set null')
    employee_id = fields.Many2one('hr.employee', string='Responsible')
    vendor_id = fields.Many2one('wm.vendor')
    issue_date = fields.Date(default=fields.Date.context_today)
    expiry_date = fields.Date(tracking=True)
    reminder_date = fields.Date()
    attachment_ids = fields.Many2many('ir.attachment', string='Documents')
    notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('valid', 'Valid'),
        ('expiring', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('renewed', 'Renewed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.compliance') or 'WM-COMP-NEW'
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('compliance_created', rec, 'Compliance record created', new_value=rec.state)
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ('expiry_date', 'state', 'attachment_ids')):
            self._update_expiry_state()
        return res

    def action_validate(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft', 'expired', 'expiring'), 'validate')
            if not rec.attachment_ids and not rec.regulation:
                raise UserError('Upload evidence or specify the regulation before validating.')
            prev = rec.state
            rec.state = 'valid'
            rec._update_expiry_state()
            self._wm_log('compliance_validated', rec, 'Compliance validated', prev, rec.state)
        return True

    def action_renew(self):
        for rec in self:
            prev = rec.state
            rec.state = 'renewed'
            self._wm_log('compliance_renewed', rec, 'Compliance renewed', prev, 'renewed')
        return True

    def _update_expiry_state(self):
        today = fields.Date.context_today(self)
        reminder_days = int(
            self.env['ir.config_parameter'].sudo().get_param('waste_management.compliance_reminder_days', '30')
        )
        for rec in self:
            if rec.state in ('cancelled', 'draft', 'renewed'):
                continue
            if not rec.expiry_date:
                continue
            if rec.expiry_date < today:
                if rec.state != 'expired':
                    prev = rec.state
                    rec.state = 'expired'
                    self._wm_log('compliance_expired', rec, 'Compliance expired', prev, 'expired')
            elif rec.expiry_date <= today + timedelta(days=reminder_days):
                if rec.state != 'expiring':
                    prev = rec.state
                    rec.state = 'expiring'
                    self._wm_log('compliance_expiring', rec, 'Compliance expiring soon', prev, 'expiring')
            elif rec.state in ('expiring', 'expired'):
                rec.state = 'valid'

    @api.model
    def cron_check_expiry(self):
        records = self.search([('state', 'in', ('valid', 'expiring', 'draft'))])
        records._update_expiry_state()
        # Create activities for expiring / expired
        for rec in records.filtered(lambda r: r.state in ('expiring', 'expired')):
            if rec.employee_id and rec.employee_id.user_id:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=rec.employee_id.user_id.id,
                    summary='Compliance %s: %s' % (rec.state, rec.title),
                    note=rec.regulation or rec.notes or '',
                )
        return True

    def to_api_dict(self):
        self.ensure_one()
        status_map = {
            'draft': ('Draft', 'info'),
            'valid': ('Compliant', 'ok'),
            'expiring': ('Expiring Soon', 'warn'),
            'expired': ('Expired', 'bad'),
            'renewed': ('Renewal In Progress', 'info'),
            'cancelled': ('Cancelled', 'bad'),
        }
        status, status_key = status_map.get(self.state, (self.state, 'info'))
        return {
            'id': self.id,
            'code': self.name,
            'name': self.title,
            'title': self.title,
            'authority': self.regulation or dict(self._fields['category'].selection).get(self.category, ''),
            'category': dict(self._fields['category'].selection).get(self.category, ''),
            'regulation': self.regulation or '',
            'site': self.entry_id.site if self.entry_id else 'All Sites',
            'vendor': self.vendor_id.name if self.vendor_id else '',
            'owner': self.employee_id.name if self.employee_id else '',
            'responsible': self.employee_id.name if self.employee_id else '',
            'issue': self._wm_date(self.issue_date),
            'expiry': self._wm_date(self.expiry_date),
            'priority': 'High' if self.state in ('expired', 'expiring') else 'Med',
            'status': status,
            'statusKey': status_key,
            'state': self.state,
        }
