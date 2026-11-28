from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HkAttendance(models.Model):
    _name = 'hk.attendance'
    _description = 'Housekeeping Attendance'
    _order = 'date desc, id desc'

    staff_id = fields.Many2one('hk.staff', required=True, ondelete='cascade', index=True)
    date = fields.Date(required=True, index=True, default=fields.Date.context_today)
    shift_id = fields.Many2one('hk.shift', ondelete='set null')
    zone_id = fields.Many2one('hk.zone', ondelete='set null')
    highlight = fields.Boolean(string='Show On Roster')
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        [
            ('present', 'Present'),
            ('absent', 'Absent'),
            ('late', 'Late'),
            ('leave', 'Leave'),
            ('off', 'Off Day'),
        ],
        default='present',
        required=True,
    )
    check_in = fields.Datetime()
    check_out = fields.Datetime()
    notes = fields.Char()

    _sql_constraints = [
        ('staff_date_uniq', 'unique(staff_id, date)', 'Attendance for this staff already exists on this date.'),
    ]

    @api.constrains('check_in', 'check_out')
    def _check_times(self):
        for line in self:
            if line.check_in and line.check_out and line.check_out < line.check_in:
                raise ValidationError('Check-out must be after check-in.')

    def action_check_in(self):
        for line in self:
            line.write({'check_in': fields.Datetime.now(), 'state': 'present' if line.state != 'late' else 'late'})
        return True

    def action_check_out(self):
        for line in self:
            if not line.check_in:
                raise ValidationError('Check-in is required before check-out.')
            line.check_out = fields.Datetime.now()
        return True
