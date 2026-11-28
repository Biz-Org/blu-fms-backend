from odoo import fields, models


class HkActivity(models.Model):
    _name = 'hk.activity'
    _description = 'Cleaning Activity'
    _order = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    frequency = fields.Selection(
        [
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('periodic', 'Periodic'),
            ('on_demand', 'On Demand'),
        ],
        default='daily',
    )
    duration = fields.Float(string='Standard Duration (hours)', default=1.0)
    checklist_template_id = fields.Many2one('hk.checklist.template', string='Default Checklist')
    active = fields.Boolean(default=True)
