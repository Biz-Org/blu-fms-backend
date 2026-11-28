# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmEntry(models.Model):
    _name = 'wm.entry'
    _description = 'Waste Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'entry_datetime desc, id desc'

    name = fields.Char(string='Title')
    code = fields.Char(string='Entry Reference', copy=False, readonly=True, default='New', tracking=True)
    waste_category = fields.Selection([
        ('dry', 'Dry/Recyclable'),
        ('wet', 'Wet/Organic'),
        ('hazardous', 'Hazardous'),
        ('ewaste', 'E-Waste'),
        ('plastic', 'Plastic'),
        ('other', 'Other'),
    ], required=True, default='dry', tracking=True)
    waste_type = fields.Char(required=True, default='General')
    product_id = fields.Many2one('product.product', string='Waste Material')
    quantity = fields.Float(required=True, default=0.0, tracking=True)
    uom_id = fields.Many2one('uom.uom', string='Unit', default=lambda self: self.env.ref('uom.product_uom_kgm', raise_if_not_found=False))
    source = fields.Char(string='Waste Source')
    department = fields.Char(string='Department / Area')
    site = fields.Char(string='Facility / Site', required=True, default='Site Alpha')
    building = fields.Char()
    floor = fields.Char()
    location_detail = fields.Char(string='Specific Location')
    location_id = fields.Many2one('stock.location', string='Storage Location')
    employee_id = fields.Many2one('hr.employee', string='Responsible Employee')
    entry_datetime = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    description = fields.Text()
    notes = fields.Text()
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], default='medium', tracking=True)
    hazardous = fields.Boolean(default=False)
    segregation_required = fields.Boolean(default=True)
    preferred_vendor_id = fields.Many2one('wm.vendor')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('recorded', 'Recorded'),
        ('pending_segregation', 'Pending Segregation'),
        ('processed', 'Processed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)
    segregation_ids = fields.One2many('wm.segregation', 'entry_id')
    schedule_ids = fields.One2many('wm.collection.schedule', 'entry_id')
    recycling_ids = fields.One2many('wm.recycling', 'entry_id')
    disposal_ids = fields.One2many('wm.disposal', 'entry_id')
    active = fields.Boolean(default=True)

    @api.constrains('quantity')
    def _check_quantity(self):
        for rec in self:
            if rec.quantity is not False and rec.quantity <= 0:
                raise ValidationError('Quantity must be greater than zero.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('wm.entry') or 'WM-ENTRY-NEW'
            if not vals.get('name'):
                vals['name'] = vals.get('waste_type') or 'Waste Entry'
            if vals.get('hazardous'):
                vals['waste_category'] = vals.get('waste_category') or 'hazardous'
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('entry_created', rec, 'Waste entry created', new_value=rec.state)
        return records

    def action_confirm(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft',), 'confirm')
            if not rec.site or not rec.waste_type:
                raise UserError('Site and waste type are required.')
            prev = rec.state
            rec.state = 'pending_segregation' if rec.segregation_required else 'recorded'
            self._wm_log('entry_confirmed', rec, 'Entry confirmed', prev, rec.state)
        return True

    def action_mark_processed(self):
        for rec in self:
            self._wm_assert_transition(rec, ('recorded', 'pending_segregation'), 'mark processed')
            prev = rec.state
            rec.state = 'processed'
            self._wm_log('entry_processed', rec, 'Entry processed', prev, 'processed')
        return True

    def action_cancel(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft', 'recorded', 'pending_segregation'), 'cancel')
            prev = rec.state
            rec.state = 'cancelled'
            self._wm_log('entry_cancelled', rec, 'Entry cancelled', prev, 'cancelled')
        return True

    def to_api_dict(self):
        self.ensure_one()
        cat_map = {
            'dry': ('Dry/Rec.', 'purple'),
            'wet': ('Wet/Org.', 'ok'),
            'hazardous': ('Hazardous', 'bad'),
            'ewaste': ('E-Waste', 'info'),
            'plastic': ('Plastic', 'info'),
            'other': ('Other', 'info'),
        }
        cat_label, cat_key = cat_map.get(self.waste_category, ('Other', 'info'))
        prio_map = {'high': 'bad', 'medium': 'warn', 'low': 'info'}
        seg_done = bool(self.segregation_ids.filtered(lambda s: s.state == 'completed'))
        col_done = bool(self.schedule_ids.filtered(lambda s: s.state in ('completed', 'in_progress', 'confirmed', 'scheduled')))
        return {
            'id': self.id,
            'priority': dict(self._fields['priority'].selection).get(self.priority, ''),
            'priorityKey': prio_map.get(self.priority, 'info'),
            'code': self.code,
            'datetime': self._wm_datetime(self.entry_datetime),
            'site': self.site or '',
            'location': self.location_detail or self.building or '',
            'category': cat_label,
            'categoryKey': cat_key,
            'type': self.waste_type or '',
            'qty': '%s %s' % (self.quantity, self.uom_id.name or 'kg'),
            'quantity': self.quantity,
            'uom': self.uom_id.name or 'kg',
            'segregation': 'Done' if seg_done else ('Pending' if self.state == 'pending_segregation' else '—'),
            'segregationKey': 'ok' if seg_done else 'warn',
            'collection': 'Scheduled' if col_done else 'Pending',
            'collectionKey': 'info' if col_done else 'warn',
            'state': self.state,
            'state_label': self._wm_selection_label(self, 'state'),
            'source': self.source or '',
            'description': self.description or '',
            'notes': self.notes or '',
            'hazardous': self.hazardous,
        }
