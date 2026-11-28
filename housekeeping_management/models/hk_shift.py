from odoo import api, fields, models


class HkShift(models.Model):
    _name = 'hk.shift'
    _description = 'Housekeeping Shift'
    _order = 'start_time, id'

    name = fields.Char(required=True)
    start_time = fields.Float(required=True)
    end_time = fields.Float(required=True)
    active = fields.Boolean(default=True)

    @api.depends('name', 'start_time', 'end_time')
    def _compute_display_name(self):
        for shift in self:
            shift.display_name = '%s (%s - %s)' % (
                shift.name,
                self._float_to_time(shift.start_time),
                self._float_to_time(shift.end_time),
            )

    @staticmethod
    def _float_to_time(value):
        value = value or 0.0
        hours = int(value) % 24
        minutes = int(round((value - int(value)) * 60))
        if minutes == 60:
            hours = (hours + 1) % 24
            minutes = 0
        return '%02d:%02d' % (hours, minutes)
