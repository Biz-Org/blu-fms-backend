import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

DONE_STATES = ('completed', 'verified', 'verification_pending')
OPEN_STATES = ('not_started', 'assigned', 'in_progress', 'rework', 'draft')


class HkDashboard(models.AbstractModel):
    """API facade for the OWL housekeeping screens."""
    _name = 'hk.dashboard'
    _description = 'Housekeeping Dashboard'

    # ------------------------------------------------------------------ helpers
    @api.model
    def _working_day(self):
        day = fields.Date.context_today(self)
        if not self.env['hk.task'].search_count([('date', '=', day)]):
            latest = self.env['hk.task'].search([], order='date desc', limit=1)
            if latest:
                day = latest.date
        return day

    @api.model
    def _format_time(self, value):
        value = value or 0.0
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes == 60:
            hours += 1
            minutes = 0
        suffix = 'AM' if hours < 12 else 'PM'
        display = hours % 12 or 12
        return f'{display:02d}:{minutes:02d} {suffix}'

    @api.model
    def _format_hhmm(self, value):
        value = value or 0.0
        hours = int(value) % 24
        minutes = int(round((value - int(value)) * 60))
        if minutes == 60:
            hours = (hours + 1) % 24
            minutes = 0
        return f'{hours:02d}:{minutes:02d}'

    @api.model
    def _format_day(self, day):
        day = fields.Date.to_date(day)
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        return f'{day.day} {months[day.month - 1]} {day.year}'

    @api.model
    def _percent(self, part, whole):
        return round((part * 100.0) / whole, 1) if whole else 0.0

    @api.model
    def _priority_label(self, value):
        return {'low': 'Low', 'medium': 'Medium', 'high': 'High'}.get(value or 'medium', 'Medium')

    # ------------------------------------------------------------------ dashboard
    @api.model
    def get_dashboard_data(self):
        Task = self.env['hk.task']
        Staff = self.env['hk.staff']
        Zone = self.env['hk.zone']
        Attendance = self.env['hk.attendance']
        day = self._working_day()
        day_domain = [('date', '=', day), ('state', '!=', 'cancelled')]
        today_tasks = Task.search_count(day_domain)
        completed = Task.search_count(day_domain + [('state', 'in', ('completed', 'verified', 'verification_pending'))])
        pending = Task.search_count(day_domain + [('state', 'in', ('not_started', 'assigned', 'rework', 'draft'))])
        overdue = Task.search_count(day_domain + [('overdue', '=', True), ('state', 'not in', DONE_STATES + ('cancelled',))])
        verification = Task.search_count(day_domain + [('state', '=', 'verification_pending')])
        in_progress = Task.search_count(day_domain + [('state', '=', 'in_progress')])
        total_staff = Staff.search_count([('active', '=', True)])
        present = Attendance.search_count([('date', '=', day), ('state', 'in', ('present', 'late'))])
        absent = Attendance.search_count([('date', '=', day), ('state', 'in', ('absent', 'leave', 'off'))])
        total_zones = Zone.with_context(active_test=False).search_count([])
        active_zones = Zone.search_count([('active', '=', True)])
        completion_rate = int(self._percent(completed, today_tasks))

        operations = []
        tasks = Task.search(day_domain + [('highlight', '=', True)], order='time_start, id', limit=20)
        if not tasks:
            tasks = Task.search(day_domain, order='time_start, id', limit=8)
        for task in tasks:
            status, label = self._task_status_ui(task)
            operations.append({
                'id': task.id,
                'name': task.name,
                'code': task.code or '',
                'zone': task.zone_id.name,
                'staff': task.staff_id.name or 'Unassigned',
                'initials': task.staff_id.initials or 'NA',
                'color': task.staff_id.color or '#7C5CFC',
                'activity': task.activity_id.name or '',
                'time': self._format_time(task.time_start),
                'time_end': self._format_time(task.time_end) if task.time_end else '',
                'priority': task.priority,
                'priority_label': self._priority_label(task.priority),
                'progress': task.progress,
                'status': status,
                'status_label': label,
            })

        alerts = []
        if overdue:
            alerts.append({'level': 'danger', 'title': f'{overdue} Tasks Overdue', 'message': 'Immediate attention required.'})
        if verification:
            alerts.append({'level': 'warning', 'title': f'{verification} Awaiting Verification', 'message': 'Supervisors needed for review.'})
        unassigned = Task.search_count(day_domain + [('staff_id', '=', False)])
        if unassigned:
            alerts.append({'level': 'info', 'title': f'{unassigned} Unassigned Tasks', 'message': 'Assign staff to balance workload.'})
        required_zones = Zone.search_count([('status', '=', 'required')])
        if required_zones:
            alerts.append({'level': 'warning', 'title': f'{required_zones} Zones Need Cleaning', 'message': 'Schedule or assign cleaning tasks.'})

        return {
            'kpis': {
                'total_staff': total_staff,
                'present': present,
                'absent': absent,
                'today_tasks': today_tasks,
                'completed': completed,
                'pending': pending,
                'overdue': overdue,
                'verification': verification,
                'in_progress': in_progress,
            },
            'operations': operations,
            'summary': {
                'present': present,
                'absent': absent,
                'total_staff': total_staff,
                'active_zones': active_zones,
                'total_zones': total_zones,
                'completed': completed,
                'completion_rate': completion_rate,
                'staff_width': self._percent(present, total_staff),
                'zone_width': self._percent(active_zones, total_zones),
            },
            'alerts': alerts or self._alerts(),
            'date_label': self._format_day(day),
        }

    @api.model
    def _task_status_ui(self, task):
        if task.overdue and task.state not in DONE_STATES + ('cancelled',):
            return 'overdue', 'OVERDUE'
        mapping = {
            'in_progress': ('in_progress', 'IN PROGRESS'),
            'assigned': ('assigned', 'ASSIGNED'),
            'not_started': ('assigned', 'NOT STARTED'),
            'completed': ('completed', 'COMPLETED'),
            'verification_pending': ('assigned', 'PENDING REVIEW'),
            'verified': ('completed', 'VERIFIED'),
            'rejected': ('overdue', 'REJECTED'),
            'rework': ('assigned', 'REWORK'),
            'draft': ('assigned', 'DRAFT'),
        }
        return mapping.get(task.state, ('assigned', (task.state or '').upper()))

    @api.model
    def _alerts(self):
        return [{'level': 'info', 'title': 'Housekeeping Ready', 'message': 'No critical alerts for today.'}]

    # ------------------------------------------------------------------ roster
    @api.model
    def get_roster_data(self):
        day = self._working_day()
        lines = self.env['hk.attendance'].search([('date', '=', day)])
        total = self.env['hk.staff'].search_count([('active', '=', True)])
        present = len(lines.filtered(lambda l: l.state == 'present'))
        away = len(lines.filtered(lambda l: l.state in ('absent', 'leave', 'off', 'late')))
        # late counted in away for absent/leave KPI? Spec: Absent/Leave - use absent+leave; late separate in present rate
        absent_leave = len(lines.filtered(lambda l: l.state in ('absent', 'leave')))
        unassigned = len(lines.filtered(lambda l: not l.zone_id or not l.shift_id))
        rate = self._percent(present + len(lines.filtered(lambda l: l.state == 'late')), total)
        variance = rate - 95.0
        rows = []
        for line in lines.sorted(lambda l: (l.sequence, l.id)):
            task = self.env['hk.task'].search([
                ('date', '=', day), ('staff_id', '=', line.staff_id.id),
                ('state', 'not in', ('cancelled', 'draft')),
            ], order='time_start', limit=1)
            shift = line.shift_id
            rows.append({
                'id': line.id,
                'staff_id': line.staff_id.id,
                'name': line.staff_id.name,
                'role': dict(line.staff_id._fields['role'].selection).get(line.staff_id.role),
                'initials': line.staff_id.initials,
                'color': line.staff_id.color or '#7C5CFC',
                'shift_name': shift.name or 'Unassigned',
                'time_start': self._format_hhmm(shift.start_time) if shift else '',
                'time_end': self._format_hhmm(shift.end_time) if shift else '',
                'zone': line.zone_id.name or 'Unassigned',
                'state': line.state,
                'state_label': dict(line._fields['state'].selection).get(line.state),
                'task': task.name or '',
            })
        return {
            'date_label': self._format_day(day),
            'facility': 'Main Facility',
            'user_name': self.env.user.name,
            'user_role': 'Operations',
            'kpis': {
                'total_staff': total,
                'present': present + len(lines.filtered(lambda l: l.state == 'late')),
                'away': absent_leave,
                'unassigned': unassigned,
                'present_rate': f'{rate:.1f}',
                'target': '95%',
                'variance': f'{variance:.1f}%',
                'present_width': rate,
            },
            'rows': rows,
            'shifts': self._shift_summary(lines),
            'alert': f'{len(lines.filtered(lambda l: l.state == "absent"))} staff absent today',
            'masters': {
                'staff': [{'id': s.id, 'name': s.name} for s in self.env['hk.staff'].search([('active', '=', True)])],
                'shifts': [{'id': s.id, 'name': s.display_name} for s in self.env['hk.shift'].search([])],
                'zones': [{'id': z.id, 'name': z.name} for z in self.env['hk.zone'].search([])],
            },
        }

    @api.model
    def _shift_summary(self, lines):
        summary = []
        colors = {'present': 'green', 'late': 'amber', 'absent': 'red', 'leave': 'purple', 'off': 'slate'}
        labels = dict(self.env['hk.attendance']._fields['state'].selection)
        for shift in self.env['hk.shift'].search([]):
            group = lines.filtered(lambda l: l.shift_id == shift)
            if not group:
                continue
            total = len(group)
            parts, segments = [], []
            for state in ('present', 'late', 'absent', 'leave', 'off'):
                count = len(group.filtered(lambda l, s=state: l.state == s))
                if not count:
                    continue
                parts.append({'label': f'{count} {labels[state]}', 'color': colors[state]})
                segments.append({'color': colors[state], 'width': round(count * 100.0 / total, 2)})
            summary.append({
                'id': shift.id,
                'name': f'{shift.name} ({self._format_hhmm(shift.start_time)} - {self._format_hhmm(shift.end_time)})',
                'count': total,
                'parts': parts,
                'segments': segments,
            })
        return summary

    @api.model
    def action_create_staff(self, vals):
        staff = self.env['hk.staff'].create({
            'name': vals.get('name'),
            'phone': vals.get('phone'),
            'email': vals.get('email'),
            'role': vals.get('role') or 'staff',
        })
        day = self._working_day()
        if not self.env['hk.attendance'].search_count([('staff_id', '=', staff.id), ('date', '=', day)]):
            self.env['hk.attendance'].create({'staff_id': staff.id, 'date': day, 'state': 'present'})
        return {'id': staff.id, 'name': staff.name}

    @api.model
    def action_assign_shift(self, attendance_id=None, staff_id=None, shift_id=None, zone_id=None, state=None):
        day = self._working_day()
        Attendance = self.env['hk.attendance']
        line = Attendance.browse(attendance_id) if attendance_id else Attendance.search([
            ('staff_id', '=', staff_id), ('date', '=', day),
        ], limit=1)
        if not line and staff_id:
            line = Attendance.create({'staff_id': staff_id, 'date': day})
        if not line:
            raise UserError('Attendance line not found.')
        vals = {}
        if shift_id:
            vals['shift_id'] = shift_id
        if zone_id is not None:
            vals['zone_id'] = zone_id or False
        if state:
            vals['state'] = state
        line.write(vals)
        return True

    @api.model
    def action_emergency_alert(self, message=None):
        users = self.env.ref('housekeeping_management.group_hk_supervisor').users | self.env.ref('housekeeping_management.group_hk_manager').users
        if not users:
            raise UserError('No supervisors/managers configured to receive emergency alerts.')
        body = message or 'Emergency Alert triggered from Housekeeping Roster.'
        partner_model = self.env['ir.model']._get('res.partner')
        for user in users:
            self.env['mail.activity'].create({
                'res_model_id': partner_model.id,
                'res_id': user.partner_id.id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': 'Housekeeping Emergency Alert',
                'note': body,
                'user_id': user.id,
            })
        return {'sent': len(users)}

    # ------------------------------------------------------------------ zones
    @api.model
    def get_zones_data(self):
        zones = self.env['hk.zone'].with_context(active_test=False).search([])
        active = zones.filtered('active')
        required = zones.filtered(lambda z: z.status == 'required')
        unassigned = zones.filtered(lambda z: not z.staff_ids)
        rows = []
        for zone in active | zones.filtered(lambda z: z.state == 'draft'):
            rows.append({
                'id': zone.id,
                'name': zone.name,
                'code': zone.code or '',
                'building': zone.building or '',
                'floor': zone.floor or '',
                'area_type': dict(zone._fields['area_type'].selection).get(zone.area_type, ''),
                'staff': len(zone.staff_ids),
                'status': zone.status,
                'status_label': dict(zone._fields['status'].selection).get(zone.status, ''),
                'priority': zone.priority,
                'priority_label': self._priority_label(zone.priority),
                'next_cleaning_date': self._format_day(zone.next_cleaning_date) if zone.next_cleaning_date else '',
            })
        daily = len(active.filtered(lambda z: z.frequency == 'daily'))
        periodic = len(active.filtered(lambda z: z.frequency in ('weekly', 'monthly', 'periodic')))
        return {
            'kpis': {
                'total': len(zones),
                'active': len(active),
                'cleaning_required': len(required),
                'unassigned': len(unassigned),
            },
            'rows': rows,
            'coverage': {
                'daily': daily,
                'daily_width': self._percent(daily, len(active) or 1),
                'periodic': periodic,
                'periodic_width': self._percent(periodic, len(active) or 1),
            },
            'alerts': [
                {'level': 'danger', 'title': f'{len(required)} zones require immediate cleaning.'},
                {'level': 'warning', 'title': f'{len(unassigned)} zones have no assigned staff.'},
            ],
            'masters': {
                'staff': [{'id': s.id, 'name': s.name} for s in self.env['hk.staff'].search([('active', '=', True)])],
            },
        }

    @api.model
    def action_save_zone(self, vals, draft=False):
        Zone = self.env['hk.zone']
        zone_id = vals.pop('id', False)
        staff_ids = vals.pop('staff_ids', []) or []
        payload = {
            'name': vals.get('name'),
            'building': vals.get('building'),
            'floor': vals.get('floor'),
            'area_type': vals.get('area_type') or 'public',
            'cleaning_type': vals.get('cleaning_type') or 'routine',
            'frequency': vals.get('frequency') or 'daily',
            'priority': (vals.get('priority') or 'medium').lower(),
            'staff_ids': [(6, 0, staff_ids)],
            'next_cleaning_date': vals.get('next_cleaning_date') or fields.Date.context_today(self),
            'state': 'draft' if draft else 'active',
            'active': not draft,
            'status': 'draft' if draft else vals.get('status') or 'required',
        }
        if vals.get('code'):
            payload['code'] = vals['code']
        if zone_id:
            zone = Zone.browse(zone_id)
            zone.write(payload)
        else:
            zone = Zone.create(payload)
        return {'id': zone.id, 'code': zone.code}

    # ------------------------------------------------------------------ schedule
    @api.model
    def get_schedule_data(self):
        day = self._working_day()
        Schedule = self.env['hk.schedule']
        schedules = Schedule.search([('active', '=', True)])
        today = schedules.filtered(lambda s: s.next_execution_date == day)
        upcoming = schedules.filtered(lambda s: s.next_execution_date and s.next_execution_date > day)
        recurring = schedules.filtered(lambda s: s.schedule_type == 'recurring' and s.state in ('active', 'confirmed'))
        overdue = schedules.filtered(lambda s: s.next_execution_date and s.next_execution_date < day and s.state in ('active', 'confirmed'))
        rows = []
        for schedule in schedules[:50]:
            staff = schedule.staff_ids[:1]
            status = 'scheduled'
            label = 'Scheduled'
            is_overdue = False
            if schedule.next_execution_date and schedule.next_execution_date < day and schedule.state in ('active', 'confirmed'):
                status, label, is_overdue = 'overdue', 'Overdue', True
            elif schedule.state == 'active':
                status, label = 'in_progress', 'In Prog'
            rows.append({
                'id': schedule.id,
                'activity': schedule.activity_id.name or schedule.name,
                'zone': schedule.zone_id.name,
                'freq': dict(schedule._fields['frequency'].selection).get(schedule.frequency, ''),
                'staff': staff.name if staff else 'Unassigned',
                'initials': staff.initials if staff else 'NA',
                'color': staff.color if staff else '#7C5CFC',
                'time': self._format_time(schedule.time_start),
                'next': self._format_day(schedule.next_execution_date) if schedule.next_execution_date else '',
                'status': status,
                'status_label': label,
                'overdue': is_overdue,
            })
        tasks_today = self.env['hk.task'].search([('date', '=', day)], order='time_start')
        upcoming_timeline = [{'time': self._format_time(t.time_start), 'title': t.name} for t in tasks_today[:8]]
        return {
            'kpis': {
                'today': len(today) or len(tasks_today),
                'upcoming': len(upcoming),
                'recurring': len(recurring),
                'overdue': len(overdue),
            },
            'rows': rows,
            'upcoming': upcoming_timeline,
            'alerts': [
                {'level': 'danger', 'title': f'{len(overdue)} Schedules Overdue', 'message': 'Action needed.'},
                {'level': 'warning', 'title': f'{len(schedules.filtered(lambda s: not s.staff_ids))} Unassigned', 'message': 'Staff needed.'},
                {'level': 'info', 'title': 'Schedules Active', 'message': f'{len(recurring)} recurring plans.'},
            ],
            'masters': self._schedule_masters(),
            'date_label': self._format_day(day),
        }

    @api.model
    def _schedule_masters(self):
        return {
            'activities': [{'id': a.id, 'name': a.name} for a in self.env['hk.activity'].search([])],
            'zones': [{'id': z.id, 'name': z.name, 'building': z.building or '', 'floor': z.floor or ''} for z in self.env['hk.zone'].search([])],
            'staff': [{'id': s.id, 'name': s.name, 'initials': s.initials} for s in self.env['hk.staff'].search([('active', '=', True)])],
            'shifts': [{'id': s.id, 'name': s.display_name} for s in self.env['hk.shift'].search([])],
            'checklists': [{'id': c.id, 'name': c.name} for c in self.env['hk.checklist.template'].search([])],
        }

    @api.model
    def action_save_schedule(self, vals, draft=False):
        Schedule = self.env['hk.schedule']
        schedule_id = vals.pop('id', False)
        staff_ids = vals.pop('staff_ids', []) or []
        days = vals.pop('days', []) or []
        payload = {
            'name': vals.get('name') or vals.get('activity_name') or 'Cleaning Schedule',
            'activity_id': vals.get('activity_id'),
            'description': vals.get('description'),
            'zone_id': vals.get('zone_id'),
            'schedule_type': 'recurring' if vals.get('mode') == 'recurring' else vals.get('schedule_type') or 'one_time',
            'frequency': (vals.get('frequency') or 'weekly').lower(),
            'repeat_days': ','.join(days) if days else vals.get('repeat_days'),
            'start_date': vals.get('start_date') or fields.Date.context_today(self),
            'end_date': vals.get('end_date') or False,
            'time_start': vals.get('time_start') if vals.get('time_start') is not None else 8.0,
            'time_end': vals.get('time_end') if vals.get('time_end') is not None else 10.0,
            'staff_ids': [(6, 0, staff_ids)],
            'shift_id': vals.get('shift_id') or False,
            'checklist_template_id': vals.get('checklist_template_id') or False,
            'priority': (vals.get('priority') or 'medium').lower(),
            'special_instructions': vals.get('instructions') or vals.get('special_instructions'),
            'state': 'draft' if draft else 'confirmed',
            'next_execution_date': vals.get('start_date') or fields.Date.context_today(self),
        }
        if not payload['activity_id']:
            raise ValidationError('Cleaning activity is required.')
        if not payload['zone_id']:
            raise ValidationError('Zone is required.')
        if schedule_id:
            schedule = Schedule.browse(schedule_id)
            schedule.write(payload)
        else:
            schedule = Schedule.create(payload)
        if not draft:
            schedule.action_generate_tasks(horizon_days=7)
        return {'id': schedule.id, 'code': schedule.code}

    # ------------------------------------------------------------------ tasks
    @api.model
    def get_tasks_data(self):
        day = self._working_day()
        Task = self.env['hk.task']
        tasks = Task.search([('date', '=', day), ('state', '!=', 'cancelled')])
        rows = []
        for task in tasks:
            status, label = self._task_status_ui(task)
            rows.append({
                'id': task.id,
                'name': task.name,
                'code': task.code or '',
                'source': dict(task._fields['source'].selection).get(task.source),
                'zone': task.zone_id.name,
                'staff': task.staff_id.name or 'Unassigned',
                'initials': task.staff_id.initials or 'NA',
                'color': task.staff_id.color or '#7C5CFC',
                'time': self._format_time(task.time_start),
                'priority': task.priority,
                'priority_label': self._priority_label(task.priority),
                'status': status if status != 'overdue' else 'overdue',
                'status_label': label,
                'progress': int(task.progress or 0),
                'state': task.state,
            })
        workload = []
        for staff in self.env['hk.staff'].search([('active', '=', True)], limit=10):
            staff_tasks = tasks.filtered(lambda t: t.staff_id == staff)
            done = len(staff_tasks.filtered(lambda t: t.state in DONE_STATES))
            pending = len(staff_tasks.filtered(lambda t: t.state in OPEN_STATES))
            workload.append({
                'name': staff.name,
                'label': f'{done} Completed' if done else f'{pending} Pending',
                'tone': 'green' if done else 'amber',
            })
        return {
            'kpis': {
                'today': len(tasks),
                'completed': len(tasks.filtered(lambda t: t.state in ('completed', 'verified', 'verification_pending'))),
                'in_progress': len(tasks.filtered(lambda t: t.state == 'in_progress')),
                'pending': len(tasks.filtered(lambda t: t.state in ('not_started', 'assigned', 'rework', 'draft'))),
                'overdue': len(tasks.filtered('overdue')),
            },
            'rows': rows,
            'workload': workload,
            'alerts': [
                {'level': 'danger', 'title': f'{len(tasks.filtered("overdue"))} tasks overdue'},
                {'level': 'warning', 'title': f'{len(tasks.filtered(lambda t: not t.staff_id))} tasks unassigned'},
                {'level': 'info', 'title': f'{len(tasks.filtered(lambda t: t.state == "in_progress"))} tasks in progress'},
            ],
            'masters': self._schedule_masters(),
        }

    @api.model
    def action_save_task(self, vals, draft=False):
        Task = self.env['hk.task']
        task_id = vals.pop('id', False)
        payload = {
            'name': vals.get('name'),
            'activity_id': vals.get('activity_id') or False,
            'description': vals.get('description'),
            'zone_id': vals.get('zone_id'),
            'staff_id': vals.get('staff_id') or False,
            'shift_id': vals.get('shift_id') or False,
            'date': vals.get('date') or fields.Date.context_today(self),
            'time_start': vals.get('time_start') if vals.get('time_start') is not None else 8.0,
            'time_end': vals.get('time_end') if vals.get('time_end') is not None else 10.0,
            'priority': (vals.get('priority') or 'medium').lower(),
            'source': 'schedule' if vals.get('mode') == 'schedule' else 'manual',
            'state': 'draft' if draft else ('assigned' if vals.get('staff_id') else 'not_started'),
            'checklist_template_id': vals.get('checklist_template_id') or False,
            'highlight': True,
        }
        if not payload['name']:
            raise ValidationError('Task name is required.')
        if not payload['zone_id']:
            raise ValidationError('Zone is required.')
        if task_id:
            task = Task.browse(task_id)
            task.write(payload)
        else:
            task = Task.create(payload)
        return {'id': task.id, 'code': task.code}

    @api.model
    def action_task_workflow(self, task_id, action, **kwargs):
        task = self.env['hk.task'].browse(task_id)
        if action == 'start':
            return task.action_start()
        if action == 'complete':
            return task.action_complete()
        if action == 'submit':
            return task.action_submit_verification()
        if action == 'approve':
            if kwargs.get('comment'):
                task.supervisor_comment = kwargs['comment']
            return task.action_approve()
        if action == 'reject':
            return task.action_reject(reason=kwargs.get('reason'), comment=kwargs.get('comment'))
        raise UserError('Unknown task action.')

    # ------------------------------------------------------------------ checklist / verification
    @api.model
    def get_checklist_data(self, task_id=None):
        Task = self.env['hk.task']
        task = Task.browse(task_id) if task_id else Task.search([
            ('state', 'in', ('in_progress', 'assigned', 'rework')),
        ], limit=1)
        if not task:
            task = Task.search([], limit=1)
        if not task:
            return {'empty': True}
        if task.checklist_template_id and not task.checklist_line_ids:
            task._generate_checklist_lines()
        sections = {}
        for line in task.checklist_line_ids:
            sections.setdefault(line.section, {'id': line.section, 'title': dict(line._fields['section'].selection).get(line.section), 'items': [], 'done': 0, 'total': 0})
            sections[line.section]['items'].append({
                'id': line.id,
                'label': line.name,
                'done': line.is_done,
                'mandatory': line.is_mandatory,
            })
            sections[line.section]['total'] += 1
            if line.is_done:
                sections[line.section]['done'] += 1
        done = len(task.checklist_line_ids.filtered('is_done'))
        total = len(task.checklist_line_ids) or 1
        return {
            'empty': False,
            'task_id': task.id,
            'task': task.name,
            'task_id_code': task.code,
            'zone': task.zone_id.name,
            'status': dict(task._fields['state'].selection).get(task.state),
            'staff': task.staff_id.name or '',
            'datetime': f'{self._format_day(task.date)}, {self._format_time(task.time_start)}',
            'priority': self._priority_label(task.priority),
            'done': done,
            'total': len(task.checklist_line_ids),
            'progress': int(self._percent(done, total)),
            'instructions': task.description or task.activity_id.description or '',
            'remarks': task.staff_remarks or '',
            'sections': list(sections.values()),
        }

    @api.model
    def action_save_checklist_progress(self, task_id, line_states=None, remarks=None):
        task = self.env['hk.task'].browse(task_id)
        for item in line_states or []:
            line = self.env['hk.task.checklist.line'].browse(item['id'])
            if line.task_id == task:
                line.write({'is_done': bool(item.get('done')), 'is_na': bool(item.get('na'))})
        if remarks is not None:
            task.staff_remarks = remarks
        return {'progress': task.progress}

    @api.model
    def action_submit_checklist(self, task_id, remarks=None):
        task = self.env['hk.task'].browse(task_id)
        if remarks is not None:
            task.staff_remarks = remarks
        if task.state == 'assigned':
            task.action_start()
        if task.state == 'in_progress':
            task.action_complete()
        return task.action_submit_verification()

    @api.model
    def get_verification_data(self):
        day = self._working_day()
        Task = self.env['hk.task']
        pending = Task.search([('state', '=', 'verification_pending')])
        approved = Task.search([('state', '=', 'verified'), ('verified_date', '>=', fields.Datetime.to_datetime(day))])
        rework = Task.search([('state', 'in', ('rework', 'rejected'))])
        rows = []
        for task in (pending | rework | approved)[:40]:
            status = 'pending' if task.state == 'verification_pending' else ('approved' if task.state == 'verified' else 'rework')
            label = {'pending': 'PENDING REVIEW', 'approved': 'APPROVED', 'rework': 'REWORK REQUIRED'}[status]
            rows.append({
                'id': task.id,
                'name': task.name,
                'zone': task.zone_id.name,
                'staff': task.staff_id.name or '',
                'completed': f"Completed · {self._format_time(task.time_end or task.time_start)}",
                'progress': f"{len(task.checklist_line_ids.filtered('is_done'))}/{len(task.checklist_line_ids) or 0}",
                'status': status,
                'status_label': label,
            })
        selected = False
        if pending:
            selected = self._verification_detail(pending[0])
        elif rows:
            selected = self._verification_detail(Task.browse(rows[0]['id']))
        return {
            'banner': f'{len(pending)} tasks are waiting for your verification.',
            'kpis': {'pending': len(pending), 'approved': len(approved), 'rework': len(rework)},
            'rows': rows,
            'selected': selected,
        }

    @api.model
    def _verification_detail(self, task):
        return {
            'id': task.id,
            'name': task.name,
            'zone': task.zone_id.name,
            'activity': task.activity_id.name or '',
            'staff': task.staff_id.name or '',
            'priority': self._priority_label(task.priority),
            'scheduled': self._format_time(task.time_start),
            'completed': self._format_time(task.time_end) if task.time_end else '',
            'checklist': task.checklist_line_ids.filtered('is_done')[:3].mapped('name'),
            'more': max(0, len(task.checklist_line_ids.filtered('is_done')) - 3),
            'progress': f"{len(task.checklist_line_ids.filtered('is_done'))}/{len(task.checklist_line_ids)} Completed",
            'issues': task.issues or 'No issues reported.',
            'remarks': task.staff_remarks or '',
            'comment': task.supervisor_comment or '',
        }

    @api.model
    def get_verification_detail(self, task_id):
        return self._verification_detail(self.env['hk.task'].browse(task_id))

    # ------------------------------------------------------------------ performance
    @api.model
    def get_performance_data(self):
        day = self._working_day()
        start = day - timedelta(days=7)
        tasks = self.env['hk.task'].search([('date', '>=', start), ('state', '!=', 'cancelled')])
        completed = tasks.filtered(lambda t: t.state in ('completed', 'verified', 'verification_pending'))
        staff_rows = []
        for staff in self.env['hk.staff'].search([('active', '=', True)]):
            st = tasks.filtered(lambda t: t.staff_id == staff)
            done = st.filtered(lambda t: t.state in ('completed', 'verified', 'verification_pending'))
            pending = st.filtered(lambda t: t.state in OPEN_STATES)
            assigned = len(st)
            staff_rows.append({
                'id': staff.id,
                'name': staff.name,
                'assigned': assigned,
                'completed': len(done),
                'pending': len(pending),
                'rate': int(self._percent(len(done), assigned or 1)),
            })
        consumables = []
        for item in self.env['hk.consumable'].search([]):
            consumables.append({
                'id': item.id,
                'name': item.name,
                'category': dict(item._fields['category'].selection).get(item.category),
                'stock': item.quantity_on_hand,
                'used': item.used_qty,
                'unit': item.unit,
                'status': item.status,
                'status_label': dict(item._fields['status'].selection).get(item.status),
            })
        low = self.env['hk.consumable'].search([('status', 'in', ('low', 'out'))])
        usages = self.env['hk.consumable.usage'].search([], limit=10)
        activities = []
        for task in self.env['hk.task'].search([], order='write_date desc', limit=5):
            activities.append({'text': f'{task.name} · {task.state}', 'time': fields.Datetime.to_string(task.write_date)})
        for usage in usages[:3]:
            activities.append({'text': f'Used {usage.quantity} {usage.unit} {usage.consumable_id.name}', 'time': self._format_day(usage.date)})
        return {
            'kpis': {
                'completed': len(completed),
                'completion_rate': int(self._percent(len(completed), len(tasks) or 1)),
                'low_stock': len(low),
                'consumables_used': int(sum(self.env['hk.consumable'].search([]).mapped('used_qty'))),
            },
            'staff': staff_rows,
            'consumables': consumables,
            'alerts': [{'level': 'danger' if i.status == 'out' else 'warning', 'title': f'{i.name} is {i.status}.'} for i in low]
                      or [{'level': 'info', 'title': 'Stock levels are healthy.'}],
            'activities': activities,
        }

    @api.model
    def action_record_consumable_usage(self, vals):
        usage = self.env['hk.consumable.usage'].create({
            'consumable_id': vals['consumable_id'],
            'quantity': vals.get('quantity') or 1,
            'task_id': vals.get('task_id') or False,
            'zone_id': vals.get('zone_id') or False,
            'staff_id': vals.get('staff_id') or False,
            'remarks': vals.get('remarks'),
        })
        return {'id': usage.id}

    # ------------------------------------------------------------------ sample bootstrap (safe)
    @api.model
    def load_sample_data(self):
        if self.env['hk.staff'].search_count([]):
            self._ensure_masters()
            return True
        day = fields.Date.context_today(self)
        shifts = self._create_shifts()
        template = self._create_default_checklist()
        activities = self._create_activities(template)
        staff = self._create_sample_staff()
        zones = self._create_sample_zones()
        self._create_attendance_plan(day, staff, zones, shifts)
        self._create_sample_tasks(day, staff, zones, activities, template, shifts)
        self._create_consumables()
        _logger.info('Housekeeping sample data loaded')
        return True

    @api.model
    def _ensure_masters(self):
        if not self.env['hk.shift'].search_count([]):
            self._create_shifts()
        if not self.env['hk.checklist.template'].search_count([]):
            template = self._create_default_checklist()
            self._create_activities(template)
        if not self.env['hk.activity'].search_count([]):
            template = self.env['hk.checklist.template'].search([], limit=1)
            self._create_activities(template)
        if not self.env['hk.consumable'].search_count([]):
            self._create_consumables()

    @api.model
    def _create_shifts(self):
        return self.env['hk.shift'].create([
            {'name': 'Morning', 'start_time': 6.0, 'end_time': 14.0},
            {'name': 'Evening', 'start_time': 14.0, 'end_time': 22.0},
            {'name': 'Night', 'start_time': 22.0, 'end_time': 6.0},
        ])

    @api.model
    def _create_default_checklist(self):
        template = self.env['hk.checklist.template'].create({'name': 'Lobby Standard Clean v2'})
        self.env['hk.checklist.item'].create([
            {'template_id': template.id, 'name': 'Remove obstacles from the cleaning area', 'section': 'pre', 'sequence': 1},
            {'template_id': template.id, 'name': 'Collect and dispose of loose waste', 'section': 'pre', 'sequence': 2},
            {'template_id': template.id, 'name': 'Prepare cleaning materials and signage', 'section': 'pre', 'sequence': 3},
            {'template_id': template.id, 'name': 'Sweep entire floor area thoroughly', 'section': 'cleaning', 'sequence': 4},
            {'template_id': template.id, 'name': 'Mop hard floors with approved cleaner', 'section': 'cleaning', 'sequence': 5},
            {'template_id': template.id, 'name': 'Wipe baseboards and corners', 'section': 'cleaning', 'sequence': 6},
            {'template_id': template.id, 'name': 'Dry mop hardwood near elevators', 'section': 'cleaning', 'sequence': 7, 'is_mandatory': False},
        ])
        return template

    @api.model
    def _create_activities(self, template):
        return self.env['hk.activity'].create([
            {'name': 'Lobby Deep Cleaning', 'checklist_template_id': template.id, 'frequency': 'daily'},
            {'name': 'Floor Cleaning', 'checklist_template_id': template.id, 'frequency': 'daily'},
            {'name': 'Washroom Cleaning', 'checklist_template_id': template.id, 'frequency': 'daily'},
            {'name': 'Parking Cleaning', 'checklist_template_id': template.id, 'frequency': 'weekly'},
            {'name': 'Clubhouse Cleaning', 'checklist_template_id': template.id, 'frequency': 'daily'},
            {'name': 'Deep Cleaning', 'checklist_template_id': template.id, 'frequency': 'periodic'},
        ])

    @api.model
    def _create_consumables(self):
        self.env['hk.consumable'].create([
            {'name': 'Floor Cleaner', 'category': 'liquid', 'unit': 'L', 'quantity_on_hand': 12, 'min_quantity': 5},
            {'name': 'Disinfectant', 'category': 'liquid', 'unit': 'L', 'quantity_on_hand': 4, 'min_quantity': 5},
            {'name': 'Garbage Bags', 'category': 'supply', 'unit': 'Pack', 'quantity_on_hand': 2, 'min_quantity': 5},
            {'name': 'Gloves', 'category': 'ppe', 'unit': 'Pair', 'quantity_on_hand': 18, 'min_quantity': 10},
        ])

    @api.model
    def _create_sample_staff(self):
        named = [
            ('Rahul Sharma', '#7C5CFC'), ('Sneha Patil', '#22A06B'), ('Amit Kumar', '#F5A524'),
            ('Neha Singh', '#E5484D'), ('Priya Shah', '#3B82F6'),
        ]
        extra = [
            'Vikram Joshi', 'Anita Desai', 'Rohan Mehta', 'Kavita Nair', 'Sanjay Gupta', 'Pooja Rao',
            'Arjun Iyer', 'Meera Kapoor', 'Nikhil Verma', 'Divya Jain', 'Karan Malhotra', 'Sonia Reddy',
            'Harsh Patel', 'Anjali Bose', 'Manish Yadav', 'Ritu Agarwal', 'Deepak Chawla', 'Neelam Kulkarni',
            'Aditya Menon', 'Shweta Pandey', 'Varun Saxena', 'Lakshmi Krishnan', 'Imran Qureshi',
            'Fatima Sheikh', 'Joseph Dsouza', 'Catherine Fernandes', 'Mohit Bansal',
        ]
        vals = [{'name': n, 'color': c, 'role': 'staff'} for n, c in named]
        vals += [{'name': n, 'role': 'staff'} for n in extra]
        return self.env['hk.staff'].create(vals)

    @api.model
    def _create_sample_zones(self):
        rows = [
            ('Main Lobby', 'Main Building', 'Ground Floor', 'lobby', 'high', True),
            ('Tower A - Floor 3', 'Tower A', 'Floor 3', 'common', 'medium', True),
            ('Tower B - Floor 2', 'Tower B', 'Floor 2', 'washroom', 'high', True),
            ('Basement P1', 'Basement', 'P1', 'parking', 'medium', True),
            ('Clubhouse', 'Clubhouse', 'Ground', 'clubhouse', 'low', True),
            ('Reception', 'Main Building', 'Ground', 'reception', 'medium', True),
            ('Garden', 'Garden', 'Ground', 'garden', 'low', True),
            ('Parking P2', 'Basement', 'P2', 'parking', 'low', True),
        ]
        return self.env['hk.zone'].create([
            {
                'name': n, 'building': b, 'floor': f, 'area_type': a, 'priority': p,
                'active': act, 'status': 'clean' if i < 2 else 'required', 'frequency': 'daily',
            }
            for i, (n, b, f, a, p, act) in enumerate(rows)
        ])

    @api.model
    def _create_attendance_plan(self, day, staff, zones, shifts):
        morning, evening, night = shifts[0], shifts[1], shifts[2]
        by_zone = {z.name: z for z in zones}
        plan = []
        for index, person in enumerate(staff):
            if index == 0:
                plan.append((person, morning, 'present', by_zone['Main Lobby'].id, True, 1))
            elif index == 1:
                plan.append((person, morning, 'present', by_zone['Tower A - Floor 3'].id, True, 2))
            elif index == 2:
                plan.append((person, morning, 'late', by_zone['Tower B - Floor 2'].id, True, 3))
            elif index == 3:
                plan.append((person, morning, 'present', by_zone['Basement P1'].id, True, 4))
            elif index == 4:
                plan.append((person, evening, 'present', by_zone['Clubhouse'].id, True, 5))
            elif index <= 17:
                zone_id = False if index in (15, 16, 17) else by_zone['Reception'].id
                plan.append((person, morning, 'present', zone_id, False, 20 + index))
            elif index == 18:
                plan.append((person, morning, 'absent', by_zone['Reception'].id, False, 38))
            elif index <= 27:
                state = 'leave' if index == 27 else 'present'
                plan.append((person, evening, state, by_zone['Garden'].id, False, 40 + index))
            else:
                state = 'off' if index == 31 else 'present'
                plan.append((person, night, state, by_zone['Parking P2'].id, False, 60 + index))
        self.env['hk.attendance'].create([
            {
                'staff_id': person.id, 'date': day, 'shift_id': shift.id, 'state': state,
                'zone_id': zone_id, 'highlight': highlight, 'sequence': sequence,
            }
            for person, shift, state, zone_id, highlight, sequence in plan
        ])

    @api.model
    def _create_sample_tasks(self, day, staff, zones, activities, template, shifts):
        by_zone = {z.name: z for z in zones}
        by_act = {a.name: a for a in activities}
        featured = [
            ('Lobby Deep Cleaning', 'Main Lobby', staff[0], 8.0, 10.0, 'completed', False, 'Lobby Deep Cleaning'),
            ('Floor Cleaning', 'Tower A - Floor 3', staff[1], 9.0, 11.0, 'in_progress', False, 'Floor Cleaning'),
            ('Washroom Cleaning', 'Tower B - Floor 2', staff[2], 10.0, 11.0, 'assigned', False, 'Washroom Cleaning'),
            ('Parking Cleaning', 'Basement P1', staff[3], 10.5, 12.0, 'assigned', True, 'Parking Cleaning'),
            ('Clubhouse Cleaning', 'Clubhouse', staff[4], 11.0, 13.0, 'completed', False, 'Clubhouse Cleaning'),
        ]
        vals = []
        for name, zone, person, start, end, state, overdue, act in featured:
            vals.append({
                'name': name, 'zone_id': by_zone[zone].id, 'staff_id': person.id, 'date': day,
                'time_start': start, 'time_end': end, 'state': state, 'highlight': True,
                'activity_id': by_act.get(act, activities[0]).id, 'checklist_template_id': template.id,
                'priority': 'high' if overdue or name.startswith('Lobby') else 'medium',
                'source': 'schedule', 'shift_id': shifts[0].id,
            })
        # fill volume
        for i in range(20):
            vals.append({
                'name': activities[i % len(activities)].name,
                'zone_id': zones[i % len(zones)].id,
                'staff_id': staff[i % 28].id,
                'date': day,
                'time_start': 6 + (i % 10),
                'time_end': 7 + (i % 10),
                'state': 'verified' if i < 12 else ('verification_pending' if i < 15 else 'assigned'),
                'activity_id': activities[i % len(activities)].id,
                'checklist_template_id': template.id,
                'source': 'manual' if i % 3 == 0 else 'schedule',
                'priority': 'medium',
            })
        tasks = self.env['hk.task'].create(vals)
        # mark some checklist done for first in-progress task
        for task in tasks.filtered(lambda t: t.state == 'in_progress')[:1]:
            task.checklist_line_ids[:3].write({'is_done': True})
        return tasks
