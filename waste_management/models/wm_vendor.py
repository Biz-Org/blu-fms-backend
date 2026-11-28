# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmVendor(models.Model):
    _name = 'wm.vendor'
    _description = 'Waste Vendor Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'name'

    name = fields.Char(related='partner_id.name', store=True, readonly=False)
    code = fields.Char(string='Vendor Code', copy=False, readonly=True, default='New', tracking=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict', tracking=True)
    phone = fields.Char(related='partner_id.phone', readonly=False)
    email = fields.Char(related='partner_id.email', readonly=False)
    vendor_type = fields.Selection([
        ('collection', 'Collection'),
        ('recycling', 'Recycling'),
        ('disposal', 'Disposal'),
        ('mixed', 'Mixed Services'),
    ], default='mixed', tracking=True)
    waste_categories = fields.Char(string='Waste Categories Handled')
    recycling_capability = fields.Boolean(default=False)
    disposal_capability = fields.Boolean(default=False)
    license_number = fields.Char()
    license_expiry = fields.Date(tracking=True)
    contract_start = fields.Date()
    contract_end = fields.Date(tracking=True)
    rating = fields.Float(default=0.0)
    notes = fields.Text()
    document_ids = fields.Many2many('ir.attachment', string='Documents')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expiring', 'Expiring'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ], default='draft', tracking=True, index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('wm_vendor_code_uniq', 'unique(code)', 'Vendor code must be unique.'),
        ('wm_vendor_partner_uniq', 'unique(partner_id)', 'This partner already has a waste vendor profile.'),
    ]

    @api.constrains('contract_start', 'contract_end', 'license_expiry')
    def _check_dates(self):
        for rec in self:
            if rec.contract_start and rec.contract_end and rec.contract_end < rec.contract_start:
                raise ValidationError('Contract end date must be after start date.')

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env['res.partner']
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('wm.vendor') or 'WM-VEN-NEW'
            if not vals.get('partner_id') and vals.get('name'):
                partner = Partner.create({
                    'name': vals['name'],
                    'phone': vals.get('phone'),
                    'email': vals.get('email'),
                    'supplier_rank': 1,
                    'company_type': 'company',
                })
                vals['partner_id'] = partner.id
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('vendor_created', rec, 'Waste vendor created', new_value=rec.state)
        return records

    def action_activate(self):
        for rec in self:
            if rec.license_expiry and rec.license_expiry < fields.Date.context_today(self):
                raise UserError('Cannot activate vendor with expired license.')
            prev = rec.state
            rec.state = 'active'
            self._wm_log('vendor_activated', rec, 'Vendor activated', prev, 'active')
        return True

    def action_suspend(self):
        self._wm_require_group('waste_management.group_wm_manager')
        for rec in self:
            prev = rec.state
            rec.state = 'suspended'
            self._wm_log('vendor_suspended', rec, 'Vendor suspended', prev, 'suspended')
        return True

    def is_operational(self):
        self.ensure_one()
        return self.active and self.state == 'active'

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'contact': self.partner_id.name or '',
            'phone': self.phone or '',
            'email': self.email or '',
            'services': self.waste_categories or '',
            'sites': self.partner_id.city or '',
            'rating': self.rating,
            'status': self._wm_selection_label(self, 'state'),
            'statusKey': 'ok' if self.state == 'active' else ('warn' if self.state == 'expiring' else 'bad' if self.state in ('suspended', 'inactive') else 'info'),
            'state': self.state,
            'vendor_type': self.vendor_type,
            'license_number': self.license_number or '',
            'license_expiry': self._wm_date(self.license_expiry),
            'contract_start': self._wm_date(self.contract_start),
            'contract_end': self._wm_date(self.contract_end),
        }

    @api.model
    def cron_scan_license_expiry(self):
        from datetime import timedelta
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=30)
        for rec in self.search([('state', 'in', ('active', 'expiring')), ('license_expiry', '!=', False)]):
            if rec.license_expiry < today:
                prev = rec.state
                rec.state = 'inactive'
                self._wm_log('vendor_license_expired', rec, 'License expired', prev, 'inactive')
            elif rec.license_expiry <= soon and rec.state == 'active':
                rec.state = 'expiring'
                self._wm_log('vendor_license_expiring', rec, 'License expiring soon', 'active', 'expiring')
        return True
