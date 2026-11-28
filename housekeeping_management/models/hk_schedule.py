from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HkSchedule(models.Model):
    _name = 'hk.schedule'
    _description = 'Cleaning Schedule'
    _order = 'next_execution_date, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Schedule ID', copy=False)
    activity_id = fields.Many2one('hk.activity', required=True)
    description = fields.Text()
    zone_id = fields.Many2one('hk.zone', required=True, tracking=True)
    building = fields.Char(related='zone_id.building', store=True)
    floor = fields.Char(related='zone_id.floor', store=True)
    schedule_type = fields.Selection(
        [('one_time', 'One-Time'), ('recurring', 'Recurring')],
        default='one_time',
        required=True,
    )
    frequency = fields.Selection(
        [
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('custom', 'Custom'),
        ],
        default='daily',
    )
    repeat_days = fields.Char(help='Comma-separated day codes: M,T,W,T2,F,S,S2')
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date()
    time_start = fields.Float(default=8.0)
    time_end = fields.Float(default=10.0)
    staff_ids = fields.Many2many('hk.staff', string='Assigned Staff')
    shift_id = fields.Many2one('hk.shift')
    checklist_template_id = fields.Many2one('hk.checklist.template')
    priority = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        default='medium',
    )
    special_instructions = fields.Text()
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        tracking=True,
    )
    next_execution_date = fields.Date(tracking=True)
    active = fields.Boolean(default=True)
    task_ids = fields.One2many('hk.task', 'schedule_id')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('hk.schedule') or '/'
            if not vals.get('name') and vals.get('activity_id'):
                activity = self.env['hk.activity'].browse(vals['activity_id'])
                vals['name'] = activity.name
            if not vals.get('next_execution_date'):
                vals['next_execution_date'] = vals.get('start_date')
            if not vals.get('checklist_template_id') and vals.get('activity_id'):
                activity = self.env['hk.activity'].browse(vals['activity_id'])
                vals['checklist_template_id'] = activity.checklist_template_id.id
        return super().create(vals_list)

    @api.constrains('start_date', 'end_date', 'time_start', 'time_end')
    def _check_dates(self):
        for schedule in self:
            if schedule.end_date and schedule.start_date and schedule.end_date < schedule.start_date:
                raise ValidationError('End date must be after start date.')
            if schedule.time_end and schedule.time_start and schedule.time_end < schedule.time_start:
                raise ValidationError('End time must be after start time.')

    def action_confirm(self):
        self.write({'state': 'confirmed', 'next_execution_date': fields.Date.context_today(self)})
        return True

    def action_activate(self):
        self.write({'state': 'active'})
        return self.action_generate_tasks()

    def action_cancel(self):
        self.write({'state': 'cancelled', 'active': False})
        return True

    def action_generate_tasks(self, horizon_days=7):
        """Generate tasks for upcoming dates only (controlled horizon)."""
        Task = self.env['hk.task']
        created = self.env['hk.task']
        today = fields.Date.context_today(self)
        for schedule in self.filtered(lambda s: s.state in ('confirmed', 'active') and s.active):
            dates = schedule._upcoming_dates(today, horizon_days)
            for day in dates:
                staff = schedule.staff_ids[:1]
                domain = [
                    ('schedule_id', '=', schedule.id),
                    ('date', '=', day),
                    ('zone_id', '=', schedule.zone_id.id),
                ]
                if Task.search_count(domain):
                    continue
                created |= Task.create({
                    'name': schedule.name or schedule.activity_id.name,
                    'activity_id': schedule.activity_id.id,
                    'description': schedule.description or schedule.special_instructions,
                    'zone_id': schedule.zone_id.id,
                    'staff_id': staff.id if staff else False,
                    'shift_id': schedule.shift_id.id,
                    'schedule_id': schedule.id,
                    'date': day,
                    'time_start': schedule.time_start,
                    'time_end': schedule.time_end,
                    'priority': schedule.priority,
                    'source': 'schedule',
                    'state': 'assigned' if staff else 'not_started',
                    'checklist_template_id': schedule.checklist_template_id.id,
                    'highlight': day == today,
                })
            if dates:
                future = [d for d in dates if d >= today]
                schedule.next_execution_date = future[0] if future else dates[-1]
            if schedule.schedule_type == 'one_time' and dates:
                schedule.state = 'completed'
            elif schedule.state == 'confirmed':
                schedule.state = 'active'
        return created

    def _upcoming_dates(self, today, horizon_days):
        self.ensure_one()
        start = max(self.start_date or today, today)
        end_horizon = today + timedelta(days=horizon_days)
        end = min(self.end_date or end_horizon, end_horizon) if self.end_date else end_horizon
        if self.schedule_type == 'one_time':
            day = self.start_date or today
            return [day] if day >= today and day <= end_horizon else []
        days = []
        cur = start
        while cur <= end:
            if self._matches_recurrence(cur):
                days.append(cur)
            cur += timedelta(days=1)
        return days

    def _matches_recurrence(self, day):
        self.ensure_one()
        if self.frequency == 'daily':
            return True
        if self.frequency == 'weekly':
            codes = (self.repeat_days or 'M,T,W,T2,F').split(',')
            map_py = {0: 'M', 1: 'T', 2: 'W', 3: 'T2', 4: 'F', 5: 'S', 6: 'S2'}
            return map_py[day.weekday()] in [c.strip() for c in codes]
        if self.frequency == 'monthly':
            return day.day == (self.start_date.day if self.start_date else 1)
        codes = (self.repeat_days or '').split(',')
        if not any(codes):
            return True
        map_py = {0: 'M', 1: 'T', 2: 'W', 3: 'T2', 4: 'F', 5: 'S', 6: 'S2'}
        return map_py[day.weekday()] in [c.strip() for c in codes if c.strip()]

    @api.model
    def _cron_generate_tasks(self):
        schedules = self.search([('state', 'in', ('confirmed', 'active')), ('active', '=', True)])
        schedules.action_generate_tasks(horizon_days=3)
