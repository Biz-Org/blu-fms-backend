from odoo import api, fields, models


class HkZone(models.Model):
    _name = 'hk.zone'
    _description = 'Housekeeping Zone'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Zone ID', copy=False, tracking=True)
    building = fields.Char(string='Building / Tower', tracking=True)
    floor = fields.Char(string='Floor / Level')
    area_type = fields.Selection(
        [
            ('lobby', 'Lobby'),
            ('public', 'Public Area'),
            ('common', 'Common Area'),
            ('washroom', 'Washroom'),
            ('parking', 'Parking'),
            ('garden', 'Garden'),
            ('gym', 'Gym'),
            ('pool', 'Swimming Pool'),
            ('clubhouse', 'Clubhouse'),
            ('corridor', 'Corridor'),
            ('reception', 'Reception'),
            ('recreation', 'Recreation'),
            ('other', 'Other'),
        ],
        string='Area Type',
        default='common',
    )
    cleaning_type = fields.Selection(
        [
            ('routine', 'Routine'),
            ('deep', 'Deep Cleaning'),
            ('sanitization', 'Sanitization'),
            ('periodic', 'Periodic'),
        ],
        default='routine',
    )
    frequency = fields.Selection(
        [
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('periodic', 'Periodic'),
            ('hourly', 'Every 4 Hours'),
        ],
        default='daily',
    )
    priority = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        default='medium',
        tracking=True,
    )
    status = fields.Selection(
        [
            ('clean', 'Clean'),
            ('in_progress', 'In Progress'),
            ('required', 'Cleaning Required'),
            ('inspection', 'Inspection Pending'),
            ('unavailable', 'Maintenance/Unavailable'),
            ('draft', 'Draft'),
        ],
        default='required',
        tracking=True,
    )
    staff_ids = fields.Many2many('hk.staff', 'hk_zone_staff_rel', 'zone_id', 'staff_id', string='Assigned Staff')
    next_cleaning_date = fields.Date()
    active = fields.Boolean(default=True)
    task_ids = fields.One2many('hk.task', 'zone_id')
    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active')],
        default='active',
        tracking=True,
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Zone ID must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('hk.zone') or '/'
            if vals.get('state') == 'draft':
                vals.setdefault('status', 'draft')
                vals.setdefault('active', False)
        return super().create(vals_list)

    def action_activate(self):
        self.write({'state': 'active', 'active': True, 'status': 'required'})
