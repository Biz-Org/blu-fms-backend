# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmDisposal(models.Model):
    _name = 'wm.disposal'
    _description = 'Waste Disposal'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'disposal_date desc, id desc'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    entry_id = fields.Many2one('wm.entry', ondelete='set null', tracking=True)
    segregation_id = fields.Many2one('wm.segregation', ondelete='set null')
    product_id = fields.Many2one('product.product', string='Waste Material')
    material = fields.Char()
    quantity = fields.Float(required=True, default=0.0)
    uom_id = fields.Many2one('uom.uom', default=lambda self: self.env.ref('uom.product_uom_kgm', raise_if_not_found=False))
    vendor_id = fields.Many2one('wm.vendor', string='Disposal Vendor', tracking=True)
    method = fields.Selection([
        ('landfill', 'Landfill'),
        ('incineration', 'Incineration'),
        ('chemical', 'Chemical Treatment'),
        ('other', 'Other'),
    ], default='landfill', tracking=True)
    disposal_date = fields.Date(default=fields.Date.context_today, tracking=True)
    location = fields.Char(string='Disposal Location')
    location_id = fields.Many2one('stock.location')
    certificate_ref = fields.Char(string='Certificate / Reference')
    attachment_ids = fields.Many2many('ir.attachment', string='Proof Documents')
    employee_id = fields.Many2one('hr.employee', string='Responsible')
    notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    @api.constrains('quantity')
    def _check_qty(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError('Disposal quantity must be greater than zero.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.disposal') or 'WM-DISP-NEW'
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('disposal_created', rec, 'Disposal record created', new_value=rec.state)
        return records

    def action_confirm(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft',), 'confirm')
            if not rec.vendor_id:
                raise UserError('Assign an authorized disposal vendor.')
            if rec.vendor_id and not rec.vendor_id.disposal_capability:
                raise UserError('Selected vendor is not marked for disposal capability.')
            prev = rec.state
            rec.state = 'confirmed'
            self._wm_log('disposal_confirmed', rec, 'Disposal confirmed', prev, 'confirmed')
        return True

    def action_complete(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft', 'confirmed'), 'complete')
            if not rec.certificate_ref and not rec.attachment_ids:
                raise UserError('Attach disposal proof or certificate reference before completing.')
            prev = rec.state
            rec.state = 'completed'
            self._wm_log('disposal_completed', rec, 'Disposal completed', prev, 'completed')
        return True

    def to_api_dict(self):
        self.ensure_one()
        status_map = {
            'draft': ('Pending Approval', 'warn'),
            'confirmed': ('Scheduled', 'info'),
            'completed': ('Completed', 'ok'),
            'cancelled': ('Rejected', 'bad'),
        }
        status, status_key = status_map.get(self.state, (self.state, 'info'))
        return {
            'id': self.id,
            'code': self.name,
            'source': self.entry_id.code if self.entry_id else '',
            'entry': self.entry_id.code if self.entry_id else '',
            'type': self.material or (self.product_id.display_name if self.product_id else ''),
            'material': self.material or (self.product_id.display_name if self.product_id else ''),
            'qty': '%s %s' % (self.quantity, self.uom_id.name or 'kg'),
            'vendor': self.vendor_id.name if self.vendor_id else '',
            'method': dict(self._fields['method'].selection).get(self.method, ''),
            'date': self._wm_date(self.disposal_date),
            'certificate': self.certificate_ref or '',
            'cost': '—',
            'status': status,
            'statusKey': status_key,
            'state': self.state,
        }
