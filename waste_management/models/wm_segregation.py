# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmSegregation(models.Model):
    _name = 'wm.segregation'
    _description = 'Waste Segregation'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    entry_id = fields.Many2one('wm.entry', required=True, ondelete='cascade', tracking=True)
    waste_category = fields.Selection(related='entry_id.waste_category', store=True)
    product_id = fields.Many2one(related='entry_id.product_id', store=True)
    original_qty = fields.Float(required=True)
    dry_qty = fields.Float(string='Dry Quantity')
    wet_qty = fields.Float(string='Wet Quantity')
    hazardous_qty = fields.Float(string='Hazardous Quantity')
    residual_qty = fields.Float(string='Residual Quantity')
    segregated_qty = fields.Float(compute='_compute_segregated', store=True)
    rejected_qty = fields.Float(default=0.0)
    uom_id = fields.Many2one(related='entry_id.uom_id', store=True)
    method = fields.Char(string='Segregation Method')
    source_location_id = fields.Many2one('stock.location')
    destination_location_id = fields.Many2one('stock.location')
    location = fields.Char(string='Segregation Location')
    employee_id = fields.Many2one('hr.employee', string='Assigned Employee')
    assignee = fields.Char()
    date_start = fields.Datetime()
    date_end = fields.Datetime()
    notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    @api.depends('dry_qty', 'wet_qty', 'hazardous_qty', 'residual_qty')
    def _compute_segregated(self):
        for rec in self:
            rec.segregated_qty = (rec.dry_qty or 0) + (rec.wet_qty or 0) + (rec.hazardous_qty or 0) + (rec.residual_qty or 0)

    @api.constrains('original_qty', 'dry_qty', 'wet_qty', 'hazardous_qty', 'residual_qty', 'rejected_qty')
    def _check_qty(self):
        for rec in self:
            if rec.original_qty <= 0:
                raise ValidationError('Original quantity must be greater than zero.')
            total = rec.segregated_qty + (rec.rejected_qty or 0)
            if total > rec.original_qty + 0.0001:
                raise ValidationError('Segregated + rejected quantity cannot exceed original quantity.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.segregation') or 'WM-SEG-NEW'
            if vals.get('entry_id') and not vals.get('original_qty'):
                entry = self.env['wm.entry'].browse(vals['entry_id'])
                vals['original_qty'] = entry.quantity
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('segregation_created', rec, 'Segregation created', new_value=rec.state)
        return records

    def action_start(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft',), 'start')
            prev = rec.state
            rec.write({'state': 'in_progress', 'date_start': fields.Datetime.now()})
            if rec.entry_id.state == 'draft':
                rec.entry_id.action_confirm()
            self._wm_log('segregation_started', rec, 'Segregation started', prev, 'in_progress')
        return True

    def action_complete(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft', 'in_progress'), 'complete')
            if rec.segregated_qty <= 0:
                raise UserError('Record segregated quantities before completing.')
            prev = rec.state
            rec.write({'state': 'completed', 'date_end': fields.Datetime.now()})
            if rec.entry_id.state == 'pending_segregation':
                rec.entry_id.action_mark_processed()
            self._wm_log('segregation_completed', rec, 'Segregation completed', prev, 'completed')
        return True

    def to_api_dict(self):
        self.ensure_one()
        entry = self.entry_id
        prio_map = {'high': 'bad', 'medium': 'warn', 'low': 'info'}
        status_map = {
            'draft': ('Pending', 'warn'),
            'in_progress': ('In Progress', 'info'),
            'completed': ('Completed', 'ok'),
            'rejected': ('Rejected', 'bad'),
            'cancelled': ('Cancelled', 'bad'),
        }
        status, status_key = status_map.get(self.state, (self.state, 'info'))
        return {
            'id': self.id,
            'priority': dict(entry._fields['priority'].selection).get(entry.priority, 'Med'),
            'priorityKey': prio_map.get(entry.priority, 'warn'),
            'code': entry.code,
            'segregation_code': self.name,
            'datetime': self._wm_datetime(self.date_start or entry.entry_datetime),
            'site': entry.site or '',
            'location': self.location or entry.location_detail or '',
            'type': entry.waste_type or '',
            'category': self._wm_selection_label(entry, 'waste_category') if entry else '',
            'qty': '%s %s' % (self.original_qty, self.uom_id.name or 'kg'),
            'status': status,
            'statusKey': status_key,
            'assignee': self.assignee or (self.employee_id.name if self.employee_id else ''),
            'original': self.original_qty,
            'segregated': self.segregated_qty,
            'residual': self.residual_qty,
            'state': self.state,
            'entry_id': entry.id,
        }
