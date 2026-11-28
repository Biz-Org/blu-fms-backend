from odoo import api, fields, models


class HkStaff(models.Model):
    _name = 'hk.staff'
    _description = 'Housekeeping Staff'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Staff ID', copy=False, tracking=True)
    phone = fields.Char()
    email = fields.Char()
    role = fields.Selection(
        [
            ('staff', 'Housekeeping Staff'),
            ('supervisor', 'Supervisor'),
            ('manager', 'Facility Manager'),
        ],
        default='staff',
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one('res.users', string='Related User')
    color = fields.Char(default='#7C5CFC')
    initials = fields.Char(compute='_compute_initials', store=True)
    active = fields.Boolean(default=True)
    attendance_ids = fields.One2many('hk.attendance', 'staff_id')
    task_ids = fields.One2many('hk.task', 'staff_id')
    zone_ids = fields.Many2many('hk.zone', 'hk_zone_staff_rel', 'staff_id', 'zone_id', string='Assigned Zones')

    @api.depends('name')
    def _compute_initials(self):
        for staff in self:
            parts = [part for part in (staff.name or '').split() if part]
            if len(parts) >= 2:
                staff.initials = (parts[0][0] + parts[-1][0]).upper()
            else:
                staff.initials = (staff.name or '')[:2].upper()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('hk.staff') or '/'
        return super().create(vals_list)
