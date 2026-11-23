from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HkConsumable(models.Model):
    _name = 'hk.consumable'
    _description = 'Housekeeping Consumable'
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(copy=False)
    category = fields.Selection(
        [
            ('liquid', 'Liquid'),
            ('supply', 'Supply'),
            ('ppe', 'PPE'),
            ('equipment', 'Equipment'),
            ('other', 'Other'),
        ],
        default='supply',
    )
    unit = fields.Char(default='Unit')
    quantity_on_hand = fields.Float(string='Available Stock', default=0.0, tracking=True)
    min_quantity = fields.Float(string='Minimum Stock', default=5.0)
    used_qty = fields.Float(compute='_compute_used', store=True)
    status = fields.Selection(
        [('ok', 'In Stock'), ('low', 'Low Stock'), ('out', 'Out of Stock')],
        compute='_compute_status',
        store=True,
    )
    active = fields.Boolean(default=True)
    usage_ids = fields.One2many('hk.consumable.usage', 'consumable_id')

    @api.depends('usage_ids.quantity')
    def _compute_used(self):
        for item in self:
            item.used_qty = sum(item.usage_ids.mapped('quantity'))

    @api.depends('quantity_on_hand', 'min_quantity')
    def _compute_status(self):
        for item in self:
            if item.quantity_on_hand <= 0:
                item.status = 'out'
            elif item.quantity_on_hand <= item.min_quantity:
                item.status = 'low'
            else:
                item.status = 'ok'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('hk.consumable') or '/'
        return super().create(vals_list)


class HkConsumableUsage(models.Model):
    _name = 'hk.consumable.usage'
    _description = 'Consumable Usage'
    _order = 'date desc, id desc'

    consumable_id = fields.Many2one('hk.consumable', required=True, ondelete='restrict')
    quantity = fields.Float(required=True, default=1.0)
    unit = fields.Char(related='consumable_id.unit', store=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    task_id = fields.Many2one('hk.task', ondelete='set null')
    zone_id = fields.Many2one('hk.zone', ondelete='set null')
    staff_id = fields.Many2one('hk.staff', ondelete='set null')
    remarks = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for line in records:
            if line.quantity <= 0:
                raise ValidationError('Usage quantity must be positive.')
            consumable = line.consumable_id
            consumable.quantity_on_hand = max(0.0, consumable.quantity_on_hand - line.quantity)
        return records
