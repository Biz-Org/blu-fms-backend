# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmRecycling(models.Model):
    _name = 'wm.recycling'
    _description = 'Waste Recycling'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'recycling_date desc, id desc'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    entry_id = fields.Many2one('wm.entry', ondelete='set null', tracking=True)
    segregation_id = fields.Many2one('wm.segregation', ondelete='set null')
    product_id = fields.Many2one('product.product', string='Product')
    material = fields.Char(string='Material')
    vendor_id = fields.Many2one('wm.vendor', string='Recycling Vendor', tracking=True)
    quantity = fields.Float(required=True, default=0.0)
    uom_id = fields.Many2one('uom.uom', default=lambda self: self.env.ref('uom.product_uom_kgm', raise_if_not_found=False))
    method = fields.Char(string='Recycling Method')
    recycling_date = fields.Date(default=fields.Date.context_today, tracking=True)
    destination = fields.Char()
    outcome = fields.Selection([
        ('success', 'Success'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ], default='success')
    employee_id = fields.Many2one('hr.employee')
    notes = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', string='Documents')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    @api.constrains('quantity')
    def _check_qty(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError('Recycling quantity must be greater than zero.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.recycling') or 'WM-REC-NEW'
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('recycling_created', rec, 'Recycling record created', new_value=rec.state)
        return records

    def action_confirm(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft',), 'confirm')
            if not rec.vendor_id:
                raise UserError('Assign a recycling vendor before confirming.')
            if rec.vendor_id and not rec.vendor_id.recycling_capability:
                raise UserError('Selected vendor is not marked for recycling capability.')
            prev = rec.state
            rec.state = 'confirmed'
            self._wm_log('recycling_confirmed', rec, 'Recycling confirmed', prev, 'confirmed')
        return True

    def action_complete(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft', 'confirmed', 'in_progress'), 'complete')
            prev = rec.state
            rec.state = 'completed'
            self._wm_log('recycling_completed', rec, 'Recycling completed', prev, 'completed')
        return True

    def to_api_dict(self):
        self.ensure_one()
        status_map = {
            'draft': ('Pending', 'warn'),
            'confirmed': ('Processing', 'info'),
            'in_progress': ('Processing', 'info'),
            'completed': ('Completed', 'ok'),
            'cancelled': ('Rejected', 'bad'),
        }
        status, status_key = status_map.get(self.state, (self.state, 'info'))
        qty_label = '%s %s' % (self.quantity, self.uom_id.name or 'kg')
        return {
            'id': self.id,
            'code': self.name,
            'source': self.entry_id.code if self.entry_id else '',
            'entry': self.entry_id.code if self.entry_id else '',
            'type': self.material or (self.product_id.display_name if self.product_id else ''),
            'material': self.material or (self.product_id.display_name if self.product_id else ''),
            'received': qty_label,
            'processed': qty_label if self.state == 'completed' else '—',
            'rejected': '—',
            'qty': qty_label,
            'vendor': self.vendor_id.name if self.vendor_id else '',
            'method': self.method or '',
            'date': self._wm_date(self.recycling_date),
            'outcome': dict(self._fields['outcome'].selection).get(self.outcome, ''),
            'status': status,
            'statusKey': status_key,
            'state': self.state,
        }
