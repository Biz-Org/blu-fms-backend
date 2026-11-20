# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import html2plaintext
from odoo.tools.misc import format_datetime

OPEN_STATES = ('new', 'open', 'assigned')
WORK_STATES = ('new', 'open', 'assigned', 'in_progress', 'pending', 'awaiting_resident', 'with_vendor', 'escalated')
RESOLVED_STATES = ('resolved', 'awaiting_verification', 'closed')
NEEDS_RESOLUTION_STATES = ('assigned', 'in_progress', 'pending', 'escalated')


class FmsHelpdeskUi(models.AbstractModel):
    """JSON API used by the PPT-matching OWL screens."""

    _name = 'fms.helpdesk.ui'
    _description = 'Helpdesk UI API'

    def _ticket(self):
        return self.env['fms.helpdesk.ticket']

    def _state_label(self, state):
        return dict(self._ticket()._fields['state'].selection).get(state, state)

    def _fmt(self, value, dt=True):
        if not value:
            return ''
        if dt:
            return format_datetime(self.env, value, dt_format='dd MMM yyyy, HH:mm')
        return format_datetime(self.env, value, dt_format='dd MMM yyyy')

    def _ago(self, value):
        if not value:
            return ''
        delta = fields.Datetime.now() - value
        minutes = int(delta.total_seconds() // 60)
        if minutes < 1:
            return _('just now')
        if minutes < 60:
            return _('%s min ago', minutes)
        hours = minutes // 60
        if hours < 24:
            return _('%s hr ago', hours)
        return _('%s days ago', hours // 24)

    def _ticket_row(self, ticket):
        priority = ticket.priority_id
        name = ticket.name or _('TKT-AUTO')
        prefix, _, number = name.partition('-')
        return {
            'id': ticket.id,
            'name': name,
            'ticket_prefix': (prefix + '-') if number else '',
            'ticket_number': number or name,
            'title': ticket.title or '',
            'resident': ticket.resident_id.name or '',
            'property': ticket.property_name or '',
            'category': ticket.category_id.name or '',
            'subcategory': ticket.subcategory_id.name or '',
            'priority': priority.name or '',
            'priority_code': priority.code or '',
            'assignee': ticket.user_id.name or ticket.team_id.name or _('Unassigned'),
            'team': ticket.team_id.name or '',
            'user_id': ticket.user_id.id,
            'team_id': ticket.team_id.id,
            'sla': ticket.sla_remaining_label or '',
            'sla_status': ticket.sla_status or '',
            'sla_breached': bool(ticket.sla_breached),
            'state': ticket.state,
            'state_label': self._state_label(ticket.state),
            'created': self._fmt(ticket.create_date, dt=False),
            'created_full': self._fmt(ticket.create_date),
            'updated': self._ago(ticket.write_date),
            'is_unassigned': bool(ticket.is_unassigned),
            'is_urgent': bool(ticket.is_urgent),
            'rating': ticket.rating or 0,
        }

    def _ticket_domain(self, params):
        domain = [('state', '!=', 'draft')] if not params.get('include_draft') else []
        search = (params.get('search') or params.get('global_search') or '').strip()
        if search:
            domain = expression.AND([domain, [
                '|', '|', '|',
                ('name', 'ilike', search),
                ('title', 'ilike', search),
                ('resident_id.name', 'ilike', search),
                ('description', 'ilike', search),
            ]])
        if params.get('state'):
            domain.append(('state', 'in', params['state'] if isinstance(params['state'], list) else [params['state']]))
        if params.get('category_id'):
            domain.append(('category_id', '=', int(params['category_id'])))
        if params.get('priority_id'):
            domain.append(('priority_id', '=', int(params['priority_id'])))
        if params.get('sla_status'):
            domain.append(('sla_status', '=', params['sla_status']))
        if params.get('team_id'):
            domain.append(('team_id', '=', int(params['team_id'])))
        if params.get('user_id'):
            domain.append(('user_id', '=', int(params['user_id'])))
        if params.get('date_from'):
            date_from = params['date_from']
            if isinstance(date_from, str) and len(date_from) == 10:
                date_from = '%s 00:00:00' % date_from
            domain.append(('create_date', '>=', date_from))
        if params.get('date_to'):
            date_to = params['date_to']
            if isinstance(date_to, str) and len(date_to) == 10:
                date_to = '%s 23:59:59' % date_to
            domain.append(('create_date', '<=', date_to))
        if params.get('property'):
            domain.append(('property_name', '=', params['property']))
        return domain

    def _masters(self):
        Category = self.env['fms.helpdesk.category']
        categories = []
        for category in Category.search([]):
            categories.append({
                'id': category.id,
                'name': category.name,
                'subcategories': [{'id': s.id, 'name': s.name} for s in category.subcategory_ids],
            })
        return {
            'categories': categories,
            'priorities': [{'id': p.id, 'name': p.name, 'code': p.code} for p in self.env['fms.helpdesk.priority'].search([])],
            'teams': [{'id': t.id, 'name': t.name} for t in self.env['fms.helpdesk.team'].search([])],
            'users': [{'id': u.id, 'name': u.name} for u in self.env['res.users'].search([('share', '=', False), ('id', '!=', 1)])],
            'sla_policies': [{'id': s.id, 'name': s.name, 'priority_id': s.priority_id.id} for s in self.env['fms.helpdesk.sla.policy'].search([])],
            'escalation_levels': [{'id': l.id, 'name': l.name, 'level': l.level} for l in self.env['fms.helpdesk.escalation.level'].search([])],
        }

    @api.model
    def bootstrap(self):
        user = self.env.user
        return {
            'user': {
                'id': user.id,
                'name': user.name,
                'login': user.login,
                'is_admin': user.has_group('fms_helpdesk.group_fms_helpdesk_admin'),
                'is_lead': user.has_group('fms_helpdesk.group_fms_helpdesk_team_lead'),
                'is_agent': user.has_group('fms_helpdesk.group_fms_helpdesk_agent'),
            },
            'app_name': self._ticket()._get_param('app_name', 'FMS Helpdesk'),
            'masters': self._masters(),
        }

    @api.model
    def load_screen(self, screen, params=None):
        params = params or {}
        method = getattr(self, '_screen_%s' % screen, None)
        if not method:
            raise UserError(_("Unknown helpdesk screen: %s", screen))
        return method(params)

    def _counts(self, Ticket, base=None):
        base = base or [('state', '!=', 'draft')]
        return {
            'total': Ticket.search_count(base),
            'open': Ticket.search_count(base + [('state', 'in', OPEN_STATES)]),
            'in_progress': Ticket.search_count(base + [('state', '=', 'in_progress')]),
            'pending': Ticket.search_count(base + [('state', 'in', ('pending', 'awaiting_resident', 'with_vendor'))]),
            'assigned': Ticket.search_count(base + [('state', '=', 'assigned')]),
            'resolved': Ticket.search_count(base + [('state', 'in', RESOLVED_STATES)]),
            'closed': Ticket.search_count(base + [('state', '=', 'closed')]),
            'new': Ticket.search_count(base + [('state', '=', 'new')]),
            'breached': Ticket.search_count(base + [('sla_breached', '=', True), ('state', 'not in', ('closed', 'draft'))]),
            'at_risk': Ticket.search_count(base + [('sla_status', '=', 'at_risk')]),
            'on_track': Ticket.search_count(base + [('sla_status', '=', 'on_track')]),
            'unassigned': Ticket.search_count(base + [('is_unassigned', '=', True), ('state', 'in', WORK_STATES)]),
            'high': Ticket.search_count(base + [('is_urgent', '=', True), ('state', 'in', WORK_STATES)]),
            'escalated': Ticket.search_count(base + [('is_escalated', '=', True)]),
        }

    def _sla_breakdown(self, tickets):
        """Shared SLA KPI math for Dashboard and Reports (same ticket set → same numbers)."""
        with_sla = tickets.filtered(lambda t: t.sla_status)
        on_track = len(with_sla.filtered(lambda t: t.sla_status == 'on_track'))
        at_risk = len(with_sla.filtered(lambda t: t.sla_status == 'at_risk'))
        breached = len(with_sla.filtered(lambda t: t.sla_breached or t.sla_status == 'breached'))
        completed = len(with_sla.filtered(lambda t: t.sla_status == 'completed'))
        denom = max(on_track + at_risk + breached + completed, 1)
        return {
            'on_track': on_track,
            'at_risk': at_risk,
            'breached': breached,
            'completed': completed,
            'compliance': round(100.0 * (on_track + completed) / denom),
            'on_track_pct': round(100.0 * on_track / denom),
            'at_risk_pct': round(100.0 * at_risk / denom),
            'breached_pct': round(100.0 * breached / denom),
        }

    def _avg_hours_label(self, tickets, field_name):
        values = [v for v in tickets.mapped(field_name) if v]
        if not values:
            return '0h 0m', 0.0
        avg = sum(values) / len(values)
        hours = int(avg)
        mins = int(round((avg - hours) * 60))
        return _('%sh %sm', hours, mins), round(avg, 2)

    def _report_domain(self, params):
        clean = {**params, 'include_draft': False}
        sla_status = clean.pop('sla_status', None)
        domain = self._ticket_domain(clean)
        if sla_status == 'breached':
            domain.append(('sla_breached', '=', True))
        elif sla_status:
            domain.append(('sla_status', '=', sla_status))
        return domain

    def _screen_dashboard(self, params):
        Ticket = self._ticket()
        base = [('state', '!=', 'draft')]
        counts = self._counts(Ticket, base)
        today = fields.Date.context_today(self)
        trend = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            start = datetime.combine(day, datetime.min.time())
            end = datetime.combine(day, datetime.max.time())
            created = Ticket.search_count(base + [('create_date', '>=', start), ('create_date', '<=', end)])
            resolved = Ticket.search_count([
                ('state', 'in', RESOLVED_STATES),
                ('resolved_date', '>=', start),
                ('resolved_date', '<=', end),
            ])
            trend.append({
                'label': day.strftime('%d %b'),
                'count': created,
                'resolved': resolved,
            })
        status = [
            {'key': 'open', 'label': _('Open'), 'count': counts['open']},
            {'key': 'assigned', 'label': _('Assigned'), 'count': counts['assigned']},
            {'key': 'in_progress', 'label': _('In Progress'), 'count': counts['in_progress']},
            {'key': 'pending', 'label': _('Pending'), 'count': counts['pending']},
            {'key': 'resolved', 'label': _('Resolved'), 'count': counts['resolved']},
        ]
        priorities = []
        for priority in self.env['fms.helpdesk.priority'].search([]):
            priorities.append({
                'code': self._priority_tone(priority),
                'name': priority.name,
                'count': Ticket.search_count(base + [('priority_id', '=', priority.id)]),
            })
        active = Ticket.search(base + [('state', 'in', WORK_STATES)])
        sla = self._sla_breakdown(Ticket.search(base))
        teams = []
        for team in self.env['fms.helpdesk.team'].search([]):
            team_open = Ticket.search_count(base + [('team_id', '=', team.id), ('state', 'in', WORK_STATES)])
            teams.append({'id': team.id, 'name': team.name, 'open': team_open})
        teams.sort(key=lambda row: row['open'], reverse=True)
        History = self.env['fms.helpdesk.ticket.history']
        activity = [{
            'id': line.id,
            'ticket_id': line.ticket_id.id,
            'ticket': line.ticket_id.name or '',
            'action': dict(line._fields['action'].selection).get(line.action, line.action),
            'user': line.user_id.name or '',
            'when': self._ago(line.date),
            'remarks': line.remarks or line.new_value or '',
        } for line in History.search([], limit=8)]
        recent = Ticket.search(base, limit=8)
        return {
            'kpis': counts,
            'trend': trend,
            'status': status,
            'priorities': priorities,
            'sla': sla,
            'teams': teams[:6],
            'activity': activity,
            'recent': [self._ticket_row(t) for t in recent],
            'active_count': len(active),
        }

    def _screen_complaints(self, params):
        Ticket = self._ticket()
        domain = self._ticket_domain(params)
        tickets = Ticket.search(domain, limit=80)
        properties = [
            name for name in Ticket.search([('state', '!=', 'draft')]).mapped('property_name') if name
        ]
        count = Ticket.search_count(domain)
        return {
            'kpis': self._counts(Ticket, [('state', '!=', 'draft')] + (
                [('property_name', '=', params['property'])] if params.get('property') else []
            ) + (
                [('create_date', '>=', params['date_from'])] if params.get('date_from') else []
            ) + (
                [('create_date', '<=', params['date_to'])] if params.get('date_to') else []
            )),
            'tickets': [self._ticket_row(t) for t in tickets],
            'count': count,
            'truncated': len(tickets) < count,
            'properties': sorted(set(properties)),
        }

    def _screen_my_complaints(self, params):
        Ticket = self._ticket()
        partner = self.env.user.partner_id
        mine = ['|', ('reported_by_id', '=', self.env.uid), ('resident_id', '=', partner.id)]
        domain = expression.AND([self._ticket_domain(params), mine])
        tickets = Ticket.search(domain, limit=80)
        base = expression.AND([
            [('state', '!=', 'draft')],
            mine,
        ])
        unit = partner.fms_unit_name or ''
        building = partner.fms_building_name or ''
        if not (unit or building) and tickets:
            unit = tickets[0].unit_name or ''
            building = tickets[0].building_name or ''
        apartment = ' - '.join(part for part in (unit, building) if part)
        return {
            'kpis': self._counts(Ticket, base),
            'tickets': [self._ticket_row(t) for t in tickets],
            'count': Ticket.search_count(domain),
            'reporter': self.env.user.name,
            'apartment': apartment,
        }

    def _screen_work_queue(self, params):
        Ticket = self._ticket()
        tab = params.get('tab') or 'mine'
        base = [('state', 'in', WORK_STATES)]
        extra = []
        if tab == 'mine':
            extra = [('user_id', '=', self.env.uid)]
        elif tab == 'unassigned':
            extra = [('is_unassigned', '=', True)]
        elif tab == 'team':
            extra = [('team_id.member_ids', 'in', [self.env.uid])]
        elif tab == 'due':
            extra = [
                ('resolution_deadline', '<=', fields.Datetime.now() + timedelta(hours=4)),
                ('sla_status', 'in', ('on_track', 'at_risk')),
            ]
        elif tab == 'breached':
            extra = [('sla_breached', '=', True)]
        elif tab == 'high':
            extra = [('is_urgent', '=', True)]
        elif tab == 'all':
            extra = []
        else:
            extra = [('user_id', '=', self.env.uid)]
        domain = base + extra
        search = (params.get('search') or params.get('global_search') or '').strip()
        if search:
            domain = expression.AND([domain, [
                '|', '|', ('name', 'ilike', search), ('title', 'ilike', search), ('resident_id.name', 'ilike', search),
            ]])
        if params.get('priority_id'):
            domain.append(('priority_id', '=', int(params['priority_id'])))
        if params.get('category_id'):
            domain.append(('category_id', '=', int(params['category_id'])))
        if params.get('sla_status'):
            domain.append(('sla_status', '=', params['sla_status']))
        tickets = Ticket.search(domain, limit=80)
        return {
            'kpis': {
                'mine': Ticket.search_count(base + [('user_id', '=', self.env.uid)]),
                'unassigned': Ticket.search_count(base + [('is_unassigned', '=', True)]),
                'due': Ticket.search_count(base + [
                    ('resolution_deadline', '<=', fields.Datetime.now() + timedelta(hours=4)),
                    ('sla_status', 'in', ('on_track', 'at_risk')),
                ]),
                'breached': Ticket.search_count(base + [('sla_breached', '=', True)]),
                'high': Ticket.search_count(base + [('is_urgent', '=', True)]),
                'all': Ticket.search_count(base),
            },
            'tickets': [self._ticket_row(t) for t in tickets],
            'count': Ticket.search_count(domain),
            'tab': tab,
            'truncated': len(tickets) < Ticket.search_count(domain),
        }

    def _screen_assignments(self, params):
        Ticket = self._ticket()
        Assignment = self.env['fms.helpdesk.assignment']
        tab = params.get('tab') or 'unassigned'
        today = fields.Date.context_today(self)
        start = datetime.combine(today, datetime.min.time())
        if tab == 'unassigned':
            domain = [('is_unassigned', '=', True), ('state', 'in', WORK_STATES)]
        elif tab == 'mine':
            domain = [('user_id', '=', self.env.uid), ('state', 'in', WORK_STATES)]
        elif tab == 'team':
            domain = [('team_id.member_ids', 'in', [self.env.uid]), ('state', 'in', WORK_STATES)]
        else:
            domain = [('state', 'in', WORK_STATES)]
        tickets = Ticket.search(domain, limit=80)
        # Full open set for Assign modal (includes already auto-assigned tickets).
        assignable = Ticket.search([('state', 'in', WORK_STATES)], limit=80, order='id desc')
        history = Assignment.search([], limit=20)
        return {
            'kpis': {
                'unassigned': Ticket.search_count([('is_unassigned', '=', True), ('state', 'in', WORK_STATES)]),
                'assigned_today': Assignment.search_count([('assign_date', '>=', start)]),
                'pending': Ticket.search_count([('state', 'in', ('pending', 'awaiting_resident'))]),
                'reassigned_today': Assignment.search_count([
                    ('assign_date', '>=', start), ('assignment_type', '=', 'reassign'),
                ]),
            },
            'tickets': [self._ticket_row(t) for t in tickets],
            'assignable_tickets': [self._ticket_row(t) for t in assignable],
            'history': [{
                'id': a.id,
                'ticket': a.ticket_id.name,
                'title': a.ticket_id.title,
                'user': a.user_id.name or '',
                'team': a.team_id.name or '',
                'type': a.assignment_type,
                'date': self._fmt(a.assign_date),
            } for a in history],
            'tab': tab,
        }

    def _screen_teams(self, params):
        Team = self.env['fms.helpdesk.team'].with_context(active_test=False)
        search = (params.get('search') or params.get('global_search') or '').strip()
        domain = []
        if search:
            domain.append(('name', 'ilike', search))
        method_labels = dict(Team._fields['assignment_method'].selection)
        rows = []
        for team in Team.search(domain):
            rows.append({
                'id': team.id,
                'name': team.name,
                'description': team.description or '',
                'leader_id': team.leader_id.id,
                'leader': team.leader_id.name or '',
                'member_ids': team.member_ids.ids,
                'members': ', '.join(team.member_ids.mapped('name')) or '—',
                'assignment_method': team.assignment_method,
                'assignment_method_label': method_labels.get(team.assignment_method, team.assignment_method),
                'open_ticket_count': team.open_ticket_count,
                'active': team.active,
            })
        return {
            'teams': rows,
            'count': len(rows),
            'kpis': {
                'total': len(rows),
                'active': len([r for r in rows if r['active']]),
                'open': sum(r['open_ticket_count'] for r in rows),
            },
        }

    @api.model
    def save_team(self, vals):
        Team = self.env['fms.helpdesk.team']
        team_id = vals.pop('id', False)
        member_ids = vals.pop('member_ids', None)
        active = vals.get('active', True)
        if isinstance(active, str):
            active = active.lower() in ('true', '1', 'yes')
        payload = {
            'name': (vals.get('name') or '').strip(),
            'description': vals.get('description') or False,
            'leader_id': int(vals['leader_id']) if vals.get('leader_id') else False,
            'assignment_method': vals.get('assignment_method') or 'manual',
            'active': bool(active),
        }
        if not payload['name']:
            raise UserError(_("Team name is required."))
        if member_ids is not None:
            payload['member_ids'] = [(6, 0, [int(x) for x in member_ids if x])]
        if team_id:
            team = Team.browse(int(team_id))
            team.write(payload)
        else:
            team = Team.create(payload)
        return {'id': team.id, 'name': team.name}

    def _screen_categories(self, params):
        Category = self.env['fms.helpdesk.category']
        search = (params.get('search') or params.get('global_search') or '').strip()
        domain = []
        if search:
            domain.append(('name', 'ilike', search))
        if params.get('status') == 'active':
            domain.append(('active', '=', True))
        elif params.get('status') == 'inactive':
            domain.append(('active', '=', False))
        categories = Category.with_context(active_test=False).search(domain)
        rows = []
        for category in categories:
            rows.append({
                'id': category.id,
                'name': category.name,
                'description': category.description or '',
                'active': category.active,
                'subcategory_count': category.subcategory_count,
                'subcategories': [s.name for s in category.subcategory_ids],
                'default_team': category.default_team_id.name or '',
                'default_team_id': category.default_team_id.id,
                'default_user_id': category.default_user_id.id,
                'routing_rule_count': category.routing_rule_count,
                'updated': self._fmt(category.write_date, dt=False),
                'rules': [{
                    'id': r.id,
                    'name': r.name,
                    'subcategory': r.subcategory_id.name or '',
                    'team': r.team_id.name or '',
                    'user': r.user_id.name or '',
                    'sla': (
                        _('%s hrs SLA', r.sla_policy_id.resolution_target)
                        if r.sla_policy_id and r.sla_policy_id.resolution_unit == 'hours'
                        else (_('%s min SLA', r.sla_policy_id.resolution_target) if r.sla_policy_id else '')
                    ),
                } for r in category.routing_rule_ids[:8]],
            })
        all_cats = Category.with_context(active_test=False).search([])
        return {
            'kpis': {
                'active': len(all_cats.filtered('active')),
                'subcategories': sum(len(c.subcategory_ids) for c in all_cats),
                'rules': sum(len(c.routing_rule_ids) for c in all_cats),
                'inactive': len(all_cats.filtered(lambda c: not c.active)),
            },
            'categories': rows,
        }

    def _fmt_duration_label(self, amount, unit):
        if not amount:
            return ''
        amount = int(amount)
        if unit == 'minutes':
            return _('%s min', amount)
        if unit == 'hours':
            return _('1 hour') if amount == 1 else _('%s hours', amount)
        if unit == 'days':
            return _('1 day') if amount == 1 else _('%s days', amount)
        return '%s %s' % (amount, unit)

    def _business_hour_rows(self):
        calendar = self.env.company.resource_calendar_id
        names = [_('Monday'), _('Tuesday'), _('Wednesday'), _('Thursday'), _('Friday'), _('Saturday'), _('Sunday')]
        hours_by_day = []
        if calendar:
            by_day = defaultdict(list)
            for att in calendar.attendance_ids:
                by_day[int(att.dayofweek)].append(att)
            for day in range(7):
                slots = by_day.get(day)
                if slots:
                    hours = ', '.join('%02d:%02d - %02d:%02d' % (
                        int(s.hour_from), int((s.hour_from % 1) * 60),
                        int(s.hour_to), int((s.hour_to % 1) * 60),
                    ) for s in sorted(slots, key=lambda s: s.hour_from))
                else:
                    hours = _('Closed (Timer Paused)')
                hours_by_day.append(hours)
        else:
            hours_by_day = [_('Closed (Timer Paused)')] * 7
        weekday = hours_by_day[:5]
        if len(set(weekday)) == 1:
            rows = [{'day': _('Mon - Fri'), 'hours': weekday[0]}]
        else:
            rows = [{'day': names[i], 'hours': hours_by_day[i]} for i in range(5)]
        rows.append({'day': _('Saturday'), 'hours': hours_by_day[5]})
        rows.append({'day': _('Sunday / Holidays'), 'hours': hours_by_day[6]})
        return rows

    def _sla_bar(self, ticket, kind):
        start = ticket.sla_start_date
        deadline = ticket.response_deadline if kind == 'response' else ticket.resolution_deadline
        done = ticket.first_response_date if kind == 'response' else (ticket.resolved_date or ticket.closed_date)
        status = ticket.response_sla_status if kind == 'response' else ticket.resolution_sla_status
        now = fields.Datetime.now()
        if not start or not deadline:
            return {'pct': 0, 'label': '', 'done': False, 'status': status or ''}
        total = max((deadline - start).total_seconds(), 1.0)
        if done:
            elapsed = max((done - start).total_seconds(), 0.0)
            mins = int(elapsed // 60)
            return {
                'pct': 100,
                'label': _('Completed (%sm)', mins),
                'done': True,
                'status': status or 'completed',
            }
        elapsed = max((now - start).total_seconds(), 0.0)
        remaining = max((deadline - now).total_seconds(), 0.0)
        rm = int(remaining // 60)
        hours, mins = divmod(rm, 60)
        return {
            'pct': min(100, max(4, int(round(elapsed / total * 100)))),
            'label': _('%02d:%02d remaining', hours, mins),
            'done': False,
            'status': status or '',
        }

    def _sla_tracker(self, ticket):
        if not ticket:
            return False
        status = ticket.sla_status or 'on_track'
        labels = {
            'on_track': _('On Track'),
            'at_risk': _('At Risk'),
            'breached': _('Breached'),
            'paused': _('Paused'),
            'completed': _('Completed'),
        }
        return {
            **self._ticket_row(ticket),
            'response_bar': self._sla_bar(ticket, 'response'),
            'resolution_bar': self._sla_bar(ticket, 'resolution'),
            'sla_badge': labels.get(status, status),
        }

    def _fmt_sla_short(self, policy):
        if not policy:
            return ''
        amount = policy.resolution_target
        unit = {
            'minutes': 'min',
            'hours': 'hr' if amount == 1 else 'hrs',
            'days': 'day' if amount == 1 else 'days',
        }.get(policy.resolution_unit, policy.resolution_unit or '')
        return '%s %s' % (amount, unit)

    def _rule_condition(self, rule):
        parts = []
        if rule.priority_id:
            parts.append(_('Priority = %s') % rule.priority_id.name)
        if rule.subcategory_id:
            parts.append(_('Subcategory = %s') % rule.subcategory_id.name)
        elif rule.category_id:
            parts.append(_('Category = %s') % rule.category_id.name)
        return ' · '.join(parts) or _('Always')

    def _screen_routing(self, params):
        Rule = self.env['fms.helpdesk.routing.rule'].with_context(active_test=False)
        all_rules = Rule.search([])
        today = fields.Date.context_today(self)
        start = datetime.combine(today, datetime.min.time())
        domain = []
        search = (params.get('search') or params.get('global_search') or '').strip()
        if search:
            domain.append('|')
            domain.append('|')
            domain.append('|')
            domain.append(('name', 'ilike', search))
            domain.append(('category_id.name', 'ilike', search))
            domain.append(('subcategory_id.name', 'ilike', search))
            domain.append(('team_id.name', 'ilike', search))
        if params.get('category_id'):
            domain.append(('category_id', '=', int(params['category_id'])))
        if params.get('priority_id'):
            domain.append(('priority_id', '=', int(params['priority_id'])))
        if params.get('team_id'):
            domain.append(('team_id', '=', int(params['team_id'])))
        status = params.get('status')
        if status == 'active':
            domain.append(('active', '=', True))
        elif status == 'inactive':
            domain.append(('active', '=', False))
        rules = Rule.search(domain)
        rows = []
        for index, rule in enumerate(rules, 1):
            rows.append({
                'id': rule.id,
                'order': index,
                'name': rule.name,
                'active': rule.active,
                'category': rule.category_id.name or '',
                'subcategory': rule.subcategory_id.name or '',
                'priority': rule.priority_id.name or '',
                'priority_code': rule.priority_id.code or '',
                'condition': self._rule_condition(rule),
                'team': rule.team_id.name or '',
                'user': rule.user_id.name or '',
                'sla': self._fmt_sla_short(rule.sla_policy_id),
                'category_id': rule.category_id.id,
                'subcategory_id': rule.subcategory_id.id,
                'priority_id': rule.priority_id.id,
                'team_id': rule.team_id.id,
                'user_id': rule.user_id.id,
                'sla_policy_id': rule.sla_policy_id.id,
            })
        return {
            'kpis': {
                'active': len(all_rules.filtered('active')),
                'inactive': len(all_rules.filtered(lambda r: not r.active)),
                'categories': len(all_rules.mapped('category_id')),
                'updated_today': Rule.search_count([('write_date', '>=', start)]),
            },
            'rules': rows,
        }

    def _screen_sla(self, params):
        Priority = self.env['fms.helpdesk.priority'].with_context(active_test=False)
        Policy = self.env['fms.helpdesk.sla.policy'].with_context(active_test=False)
        search = (params.get('search') or params.get('global_search') or '').strip()
        levels = []
        for priority in Priority.search([]):
            policy = Policy.search([('priority_id', '=', priority.id)], limit=1)
            level = priority.escalation_level_id
            row = {
                'id': priority.id,
                'name': priority.name,
                'code': priority.code,
                'description': priority.description or '',
                'response': self._fmt_duration_label(policy.response_target, policy.response_unit) if policy else '',
                'resolution': self._fmt_duration_label(policy.resolution_target, policy.resolution_unit) if policy else '',
                'escalation': _('Level %s', level.level) if level else '',
                'escalation_level_id': level.id,
                'active': priority.active,
                'policy_id': policy.id,
                'response_target': policy.response_target if policy else 30,
                'response_unit': policy.response_unit if policy else 'minutes',
                'resolution_target': policy.resolution_target if policy else 4,
                'resolution_unit': policy.resolution_unit if policy else 'hours',
            }
            if search:
                blob = ' '.join([row['name'], row['description'], row['escalation']]).lower()
                if search.lower() not in blob:
                    continue
            levels.append(row)
        policies = []
        for p in Policy.search([]):
            row = {
                'id': p.id,
                'name': p.name,
                'description': p.description or '',
                'priority': p.priority_id.name,
                'priority_code': p.priority_id.code or '',
                'priority_id': p.priority_id.id,
                'response': self._fmt_duration_label(p.response_target, p.response_unit),
                'resolution': self._fmt_duration_label(p.resolution_target, p.resolution_unit),
                'response_target': p.response_target,
                'response_unit': p.response_unit,
                'resolution_target': p.resolution_target,
                'resolution_unit': p.resolution_unit,
                'active': p.active,
                'coverage': '24×7' if p.coverage == '24x7' else _('Business Hours'),
                'coverage_code': p.coverage,
                'warning_threshold': p.warning_threshold,
                'escalation_level_id': p.escalation_level_id.id,
            }
            if search and search.lower() not in ('%s %s' % (row['name'], row['priority'])).lower():
                continue
            policies.append(row)
        all_priorities = Priority.search([])
        all_policies = Policy.search([])
        Ticket = self._ticket()
        tickets = Ticket.search([('state', 'not in', ('draft',))], limit=40)
        ICP = self.env['ir.config_parameter'].sudo()
        at_risk = int(ICP.get_param('fms_helpdesk.sla_at_risk_percent', '80') or 80)
        critical = int(ICP.get_param('fms_helpdesk.sla_critical_warning_percent', '90') or 90)
        pause_awaiting = any(all_policies.mapped('pause_on_awaiting_resident')) if all_policies else False
        pause_vendor = any(all_policies.mapped('pause_on_with_vendor')) if all_policies else False
        pauses = []
        if pause_awaiting:
            pauses.append(_('Awaiting Resident'))
        if pause_vendor:
            pauses.append(_('With Vendor'))
        return {
            'kpis': {
                'priorities': len(all_priorities),
                'policies': len(all_policies),
                'thresholds': 2 if all_policies else 0,
                'coverage': '24×7' if any(p.coverage == '24x7' for p in all_policies) else ( _('Business Hours') if all_policies else '—' ),
            },
            'levels': levels,
            'policies': policies,
            'attendances': self._business_hour_rows(),
            'pauses': pauses,
            'settings': {
                'at_risk': at_risk,
                'critical_warning': critical,
                'pause_awaiting': pause_awaiting,
                'pause_vendor': pause_vendor,
            },
            'tickets': [{'id': t.id, 'name': t.name, 'title': t.title or ''} for t in tickets],
        }

    def _needs_escalation_domain(self):
        return [
            ('state', 'not in', ('draft', 'closed', 'resolved', 'awaiting_verification')),
            ('is_escalated', '=', False),
            '|', ('sla_status', 'in', ('at_risk', 'breached')), ('is_urgent', '=', True),
        ]

    def _esc_ticket_filters(self, params):
        domain = []
        search = (params.get('search') or params.get('global_search') or '').strip()
        if search:
            domain = expression.AND([domain, [
                '|', '|',
                ('name', 'ilike', search),
                ('title', 'ilike', search),
                ('user_id.name', 'ilike', search),
            ]])
        if params.get('priority_id'):
            domain.append(('priority_id', '=', int(params['priority_id'])))
        if params.get('category_id'):
            domain.append(('category_id', '=', int(params['category_id'])))
        if params.get('team_id'):
            domain.append(('team_id', '=', int(params['team_id'])))
        return domain

    def _esc_reason_for_ticket(self, ticket):
        if ticket.sla_breached or ticket.sla_status == 'breached':
            return 'sla_breached'
        if ticket.sla_status == 'at_risk':
            return 'sla_at_risk'
        if ticket.is_urgent:
            return 'critical_priority'
        return 'manual'

    def _esc_level_label(self, level):
        if not level:
            return ''
        name = level.name or _('Level %s', level.level)
        if ' - ' in name:
            left, right = name.split(' - ', 1)
            short = right if len(right) <= 14 else (right[:12] + '..')
            return '%s (%s)' % (left, short)
        return name

    def _esc_sla_clock(self, ticket):
        if ticket.sla_breached or ticket.sla_status == 'breached':
            return _('Breached'), 'breached'
        deadline = ticket.resolution_deadline or ticket.response_deadline
        now = fields.Datetime.now()
        if deadline:
            remaining = int((deadline - now).total_seconds())
            if remaining <= 0:
                return _('Breached'), 'breached'
            hours, rem = divmod(remaining, 3600)
            mins = rem // 60
            return '%02d:%02d remaining' % (hours, mins), 'remaining'
        return ticket.sla_remaining_label or '—', ticket.sla_status or 'none'

    def _priority_tone(self, priority):
        blob = '%s %s' % (priority.code or '', priority.name or '')
        blob = blob.lower()
        for tone in ('critical', 'high', 'medium', 'low'):
            if tone in blob:
                return tone
        return (priority.code or 'medium').lower()

    def _esc_row(self, ticket, reason_code, level, action, escalation=False):
        Escalation = self.env['fms.helpdesk.escalation']
        labels = dict(Escalation._fields['reason'].selection)
        sla, sla_kind = self._esc_sla_clock(ticket)
        row = self._ticket_row(ticket)
        row.update({
            'priority_code': self._priority_tone(ticket.priority_id),
            'row_id': ('e-%s' % escalation.id) if escalation else ('t-%s' % ticket.id),
            'escalation_id': escalation.id if escalation else False,
            'reason': labels.get(reason_code) or reason_code,
            'reason_code': reason_code,
            'level': self._esc_level_label(level),
            'sla': sla,
            'sla_kind': sla_kind,
            'action': action,
        })
        return row

    def _screen_escalations(self, params):
        Ticket = self._ticket()
        Escalation = self.env['fms.helpdesk.escalation']
        tab = params.get('tab') or 'needs'
        today = fields.Date.context_today(self)
        start = datetime.combine(today, datetime.min.time())
        extra = self._esc_ticket_filters(params)
        reason_filter = params.get('reason') or ''
        if tab == 'needs':
            tickets = Ticket.search(expression.AND([self._needs_escalation_domain(), extra]), limit=80)
            rows = []
            for ticket in tickets:
                code = self._esc_reason_for_ticket(ticket)
                if reason_filter and code != reason_filter:
                    continue
                level = ticket.priority_id.escalation_level_id or self.env['fms.helpdesk.escalation.level'].search([], limit=1)
                rows.append(self._esc_row(ticket, code, level, 'escalate'))
        else:
            esc_domain = [('state', 'in', ('open', 'in_progress'))] if tab == 'escalated' else [('state', '=', 'resolved')]
            if reason_filter:
                esc_domain.append(('reason', '=', reason_filter))
            if extra:
                esc_domain.append(('ticket_id', 'in', Ticket.search(extra).ids or [0]))
            action = 'review' if tab == 'escalated' else 'view'
            rows = []
            for esc in Escalation.search(esc_domain, limit=80):
                rows.append(self._esc_row(esc.ticket_id, esc.reason, esc.level_id, action, escalation=esc))
        open_tickets = Ticket.search([
            ('state', 'in', WORK_STATES + ('resolved', 'awaiting_verification')),
        ], limit=80, order='id desc')
        return {
            'kpis': {
                'needs': Ticket.search_count(self._needs_escalation_domain()),
                'at_risk': Ticket.search_count([
                    ('sla_status', '=', 'at_risk'),
                    ('state', 'not in', ('draft', 'closed')),
                ]),
                'breached': Ticket.search_count([
                    ('sla_breached', '=', True),
                    ('state', 'not in', ('draft', 'closed')),
                ]),
                'today': Escalation.search_count([('escalation_date', '>=', start)]),
                'awaiting': Escalation.search_count([('state', 'in', ('open', 'in_progress'))]),
            },
            'rows': rows,
            'tab': tab,
            'escalate_tickets': [
                {'id': t.id, 'name': '%s — %s' % (t.name, t.title or '')}
                for t in open_tickets
            ],
        }

    @api.model
    def list_escalatable_tickets(self):
        """Open/working tickets that can still be escalated (not draft/closed)."""
        Ticket = self._ticket()
        tickets = Ticket.search([
            ('state', 'in', WORK_STATES + ('resolved', 'awaiting_verification')),
        ], limit=80, order='id desc')
        return [{
            'id': t.id,
            'name': '%s — %s' % (t.name or _('TKT'), t.title or ''),
        } for t in tickets]

    def _res_sla_label(self, ticket):
        status = ticket.sla_status or ''
        if ticket.state == 'closed' or status == 'completed':
            return _('Completed'), 'completed'
        if ticket.sla_breached or status == 'breached':
            return _('SLA Breached'), 'breached'
        deadline = ticket.resolution_deadline or ticket.response_deadline
        clock = ''
        if deadline:
            remaining = int((deadline - fields.Datetime.now()).total_seconds())
            if remaining <= 0:
                return _('SLA Breached'), 'breached'
            hours, rem = divmod(remaining, 3600)
            mins = rem // 60
            clock = '%02d:%02d' % (hours, mins)
        if status == 'at_risk':
            return (_('%s (At Risk)', clock) if clock else _('At Risk')), 'at_risk'
        if status == 'paused':
            return _('Paused'), 'paused'
        return (_('%s (On Track)', clock) if clock else _('On Track')), 'on_track'

    def _res_row(self, ticket):
        row = self._ticket_row(ticket)
        sla, kind = self._res_sla_label(ticket)
        resolution_state = ticket.resolution_id.state if ticket.resolution_id else False
        if ticket.state == 'resolved' or (
                ticket.state == 'awaiting_verification' and resolution_state == 'verified'):
            action = 'close'
        elif ticket.state == 'awaiting_verification':
            action = 'verify'
        else:
            action = 'resolve'
        row.update({
            'priority_code': self._priority_tone(ticket.priority_id),
            'sla': sla,
            'sla_kind': kind,
            'action': action,
            'resolution_state': resolution_state or '',
        })
        return row

    def _res_ticket_filters(self, params):
        domain = []
        search = (params.get('search') or params.get('global_search') or '').strip()
        if search:
            domain = expression.AND([domain, [
                '|', '|',
                ('name', 'ilike', search),
                ('title', 'ilike', search),
                ('user_id.name', 'ilike', search),
            ]])
        if params.get('category_id'):
            domain.append(('category_id', '=', int(params['category_id'])))
        if params.get('priority_id'):
            domain.append(('priority_id', '=', int(params['priority_id'])))
        if params.get('user_id'):
            domain.append(('user_id', '=', int(params['user_id'])))
        if params.get('sla_status'):
            domain.append(('sla_status', '=', params['sla_status']))
        return domain

    def _screen_resolution(self, params):
        Ticket = self._ticket()
        Resolution = self.env['fms.helpdesk.resolution']
        tab = params.get('tab') or 'needs'
        today = fields.Date.context_today(self)
        start = datetime.combine(today, datetime.min.time())
        verified_awaiting = [
            ('state', '=', 'awaiting_verification'),
            ('resolution_id.state', '=', 'verified'),
        ]
        unverified_awaiting = [
            ('state', '=', 'awaiting_verification'),
            '|', ('resolution_id', '=', False), ('resolution_id.state', '!=', 'verified'),
        ]
        if tab == 'needs':
            domain = [('state', 'in', NEEDS_RESOLUTION_STATES)]
        elif tab == 'verify':
            domain = unverified_awaiting
        elif tab == 'close':
            domain = ['|', ('state', '=', 'resolved'), '&'] + verified_awaiting
        else:
            domain = [('state', 'in', ('resolved', 'awaiting_verification', 'closed'))]
        extra = self._res_ticket_filters(params)
        if extra:
            domain = expression.AND([domain, extra])
        tickets = Ticket.search(domain, limit=80)
        recent = Resolution.search([], limit=10)
        resolve_pool = Ticket.search([('state', 'in', NEEDS_RESOLUTION_STATES)], limit=80)
        close_ready_count = Ticket.search_count([
            '|', ('state', '=', 'resolved'),
            '&', ('state', '=', 'awaiting_verification'), ('resolution_id.state', '=', 'verified'),
        ])
        return {
            'kpis': {
                'needs': Ticket.search_count([('state', 'in', NEEDS_RESOLUTION_STATES)]),
                'verify': Ticket.search_count(unverified_awaiting),
                'close': close_ready_count,
                'closed_today': Ticket.search_count([('closed_date', '>=', start)]),
                'resolved_count': Resolution.search_count([]),
                'closed_count': Ticket.search_count([('state', '=', 'closed')]),
            },
            'tickets': [self._res_row(t) for t in tickets],
            'recent': [{
                'id': r.id,
                'ticket': r.ticket_id.name,
                'title': r.ticket_id.title,
                'by': r.resolved_by_id.name,
                'text': (html2plaintext(r.description or '') or '')[:80],
                'date': self._fmt(r.resolved_date),
                'state': r.ticket_id.state,
                'state_label': self._state_label(r.ticket_id.state),
                'ticket_id': r.ticket_id.id,
            } for r in recent],
            'resolve_tickets': [
                {'id': t.id, 'name': '%s — %s' % (t.name, t.title or '')}
                for t in resolve_pool
            ],
            'tab': tab,
        }

    def _screen_feedback(self, params):
        Feedback = self.env['fms.helpdesk.feedback']
        Ticket = self._ticket()
        # Backfill pending feedback for already-closed tickets created with contact name only.
        if Ticket._get_bool_param('feedback_enabled'):
            closed = Ticket.search([('state', '=', 'closed')], limit=80, order='id desc')
            for ticket in closed:
                ticket._request_feedback()
        tab = params.get('tab') or 'pending'
        if tab == 'pending':
            records = Feedback.search([('state', '=', 'pending')], limit=80)
        elif tab == 'received':
            records = Feedback.search([('state', 'in', ('submitted', 'reviewed'))], limit=80)
        else:
            records = Feedback.search([], limit=80)
        submitted = Feedback.search([('state', 'in', ('submitted', 'reviewed'))])
        avg = round(sum(submitted.mapped('rating_value')) / len(submitted), 1) if submitted else 0
        stars = {n: len(submitted.filtered(lambda f: f.rating_value == n)) for n in range(1, 6)}
        low = Feedback.search([('is_low_rating', '=', True), ('state', '!=', 'pending')], limit=6)
        return {
            'kpis': {
                'pending': Feedback.search_count([('state', '=', 'pending')]),
                'received': len(submitted),
                'average': avg,
                'low': Feedback.search_count([('is_low_rating', '=', True), ('state', '!=', 'pending')]),
            },
            'rows': [{
                'id': f.id,
                'ticket_id': f.ticket_id.id,
                'ticket': f.ticket_id.name,
                'title': f.ticket_id.title,
                'category': f.category_id.name or '',
                'resolved_by': f.resolved_by_id.name or '',
                'date': self._fmt(f.ticket_id.resolved_date or f.request_date, dt=False),
                'state': f.state,
                'rating': f.rating_value,
            } for f in records],
            'stars': stars,
            'low': [{
                'id': f.id,
                'ticket_id': f.ticket_id.id,
                'ticket': f.ticket_id.name,
                'title': f.ticket_id.title,
                'rating': f.rating_value,
            } for f in low],
            'tab': tab,
        }

    def _screen_reports(self, params):
        Ticket = self._ticket()
        Escalation = self.env['fms.helpdesk.escalation']
        domain = self._report_domain(params)
        tickets = Ticket.search(domain)
        resolved = tickets.filtered(lambda t: t.state in RESOLVED_STATES)
        open_tickets = tickets.filtered(lambda t: t.state not in RESOLVED_STATES and t.state != 'draft')
        avg_label, avg_value = self._avg_hours_label(resolved, 'resolution_hours')
        avg_resp_label, avg_resp_value = self._avg_hours_label(
            tickets.filtered(lambda t: t.response_hours), 'response_hours')
        by_cat = []
        for category in tickets.mapped('category_id'):
            by_cat.append({
                'id': category.id,
                'name': category.name,
                'count': len(tickets.filtered(lambda t, c=category: t.category_id == c)),
            })
        by_cat.sort(key=lambda r: r['count'], reverse=True)
        sla = self._sla_breakdown(tickets)
        teams = []
        for team in tickets.mapped('team_id'):
            team_tickets = tickets.filtered(lambda t, tm=team: t.team_id == tm)
            teams.append({
                'id': team.id,
                'name': team.name,
                'total': len(team_tickets),
                'resolved': len(team_tickets.filtered(lambda t: t.state in RESOLVED_STATES)),
                'breached': len(team_tickets.filtered(lambda t: t.sla_breached)),
                'unassigned': len(team_tickets.filtered(lambda t: t.is_unassigned)),
            })
        teams.sort(key=lambda r: r['total'], reverse=True)
        today = fields.Date.context_today(self)
        volume = []
        for i in range(13, -1, -1):
            day = today - timedelta(days=i)
            start = datetime.combine(day, datetime.min.time())
            end = datetime.combine(day, datetime.max.time())
            volume.append({
                'label': day.strftime('%d %b'),
                'created': len(tickets.filtered(
                    lambda t, s=start, e=end: t.create_date and s <= t.create_date <= e)),
                'resolved': len(tickets.filtered(
                    lambda t, s=start, e=end: t.resolved_date and s <= t.resolved_date <= e)),
            })
        esc_domain = [('ticket_id', 'in', tickets.ids)] if tickets else [('id', '=', 0)]
        escalations = Escalation.search(esc_domain)
        by_reason = {}
        for esc in escalations:
            key = dict(esc._fields['reason'].selection).get(esc.reason, esc.reason)
            by_reason[key] = by_reason.get(key, 0) + 1
        reopen_count = len(tickets.filtered(lambda t: t.reopen_count > 0))
        return {
            'kpis': {
                'total': len(tickets),
                'resolved': len(resolved),
                'open': len(open_tickets),
                'compliance': sla['compliance'],
                'avg': avg_label,
                'avg_value': avg_value,
                'avg_response': avg_resp_label,
                'avg_response_value': avg_resp_value,
                'escalations': len(escalations),
                'reopened': reopen_count,
                'breached': sla['breached'],
                'at_risk': sla['at_risk'],
            },
            'by_category': by_cat[:8],
            'volume': volume,
            'sla': {
                'on_track': sla['on_track_pct'],
                'at_risk': sla['at_risk_pct'],
                'breached': sla['breached_pct'],
                'counts': sla,
            },
            'teams': teams,
            'escalation_reasons': [{'name': name, 'count': count} for name, count in by_reason.items()],
            'export_rows': [{
                'name': t.name or '',
                'title': t.title or '',
                'category': t.category_id.name or '',
                'priority': t.priority_id.name or '',
                'team': t.team_id.name or '',
                'assignee': t.user_id.name or '',
                'state': self._state_label(t.state),
                'sla_status': t.sla_status or '',
                'sla_breached': 'yes' if t.sla_breached else 'no',
                'resolution_hours': t.resolution_hours or 0,
                'created': self._fmt(t.create_date),
            } for t in tickets[:500]],
        }

    @api.model
    def export_report_rows(self, params=None):
        data = self._screen_reports(params or {})
        return data.get('export_rows') or []

    def _screen_ticket(self, params):
        ticket = self._ticket().browse(int(params.get('ticket_id') or 0))
        if not ticket.exists():
            raise UserError(_("Ticket not found."))
        attachments = [{
            'id': a.id,
            'name': a.name,
            'size': a.file_size,
            'url': '/web/content/%s?download=true' % a.id,
        } for a in ticket.attachment_ids]
        action_labels = dict(self.env['fms.helpdesk.ticket.history']._fields['action'].selection)
        history = [{
            'id': h.id,
            'date': self._fmt(h.date, dt=True),
            'time': format_datetime(self.env, h.date, dt_format='HH:mm') if h.date else '',
            'user': h.user_id.name or '',
            'action': action_labels.get(h.action, h.action),
            'remarks': h.remarks or '',
            'field': h.field_label or '',
            'old': h.old_value or '',
            'new': h.new_value or '',
        } for h in ticket.history_ids[:20]]
        return {
            'ticket': {
                **self._ticket_row(ticket),
                'description': html2plaintext(ticket.description or '') or '',
                'building': ticket.building_name or '',
                'unit': ticket.unit_name or '',
                'location': ' — '.join(filter(None, [ticket.building_name, ticket.unit_name])),
                'created_by': ticket.reported_by_id.name or '',
                'assigned_on': self._fmt(ticket.assigned_date, dt=False),
                'response_deadline': self._fmt(ticket.response_deadline),
                'resolution_deadline': self._fmt(ticket.resolution_deadline),
                'sla_policy': ticket.sla_policy_id.name or '',
                'escalation_level': ticket.escalation_level_id.name or '',
                'resolution': html2plaintext(ticket.resolution_id.description or '') if ticket.resolution_id else '',
                'resolution_state': ticket.resolution_id.state if ticket.resolution_id else '',
            },
            'attachments': attachments,
            'history': history,
        }

    def _screen_create(self, params):
        default_priority = self._ticket()._get_default_priority()
        return {
            'defaults': {
                'priority_id': default_priority.id,
                'priority_code': default_priority.code,
                'contact_method': 'app',
            },
            'preview': self.preview_ticket(params.get('vals') or {}),
        }

    def _screen_settings(self, params):
        Ticket = self._ticket()
        return {
            'app_name': Ticket._get_param('app_name', 'FMS Helpdesk'),
            'default_priority_id': Ticket._get_int_param('default_priority_id'),
            'auto_routing': Ticket._get_bool_param('auto_routing'),
            'require_verification': Ticket._get_bool_param('require_verification'),
            'allow_reopen': Ticket._get_bool_param('allow_reopen'),
            'reopen_days': Ticket._get_int_param('reopen_days'),
            'allow_resident_attachments': Ticket._get_bool_param('allow_resident_attachments'),
            'allow_multiple_attachments': Ticket._get_bool_param('allow_multiple_attachments'),
            'feedback_enabled': Ticket._get_bool_param('feedback_enabled'),
            'low_rating_threshold': Ticket._get_int_param('low_rating_threshold') or 2,
            'sequence_prefix': 'HD-',
            'timezone': self.env.user.tz or 'Asia/Kolkata',
        }

    @api.model
    def preview_ticket(self, vals):
        vals = dict(vals or {})
        # UI-only payload keys (not ticket fields)
        vals.pop('attachments', None)
        vals.pop('id', None)
        Ticket = self._ticket()
        known = set(Ticket._fields)
        vals = {key: value for key, value in vals.items() if key in known}
        vals.setdefault('title', _('Preview'))
        vals.setdefault('state', 'draft')
        ticket = Ticket.new(vals)
        return {
            'ticket_label': ticket.preview_ticket_label or _('TKT-AUTO'),
            'category': ticket.category_id.name or '--',
            'priority': ticket.priority_id.name or '',
            'priority_code': ticket.priority_id.code or 'medium',
            'response': ticket.preview_response_label or _('-- min'),
            'resolution': ticket.preview_resolution_label or _('-- hrs'),
            'team': ticket.preview_team_id.name or _('Pending Category Selection'),
            'user': ticket.preview_user_id.name or '',
            'mode': ticket.preview_assignment_mode or _('Automatic (Round Robin)'),
            'rule': ticket.preview_rule_id.name or '',
        }

    @api.model
    def search_residents(self, name):
        partners = self.env['res.partner'].search([
            ('fms_is_resident', '=', True),
            ('name', 'ilike', name or ''),
        ], limit=12)
        return [{
            'id': p.id,
            'name': p.name,
            'unit': p.fms_unit_name or '',
            'building': p.fms_building_name or '',
            'property': p.fms_property_name or '',
            'phone': p.phone or p.mobile or '',
            'email': p.email or '',
        } for p in partners]

    @api.model
    def save_ticket(self, vals, submit=False):
        Ticket = self._ticket()
        vals = dict(vals or {})
        ticket_id = vals.pop('id', False)
        files = vals.pop('attachments', []) or []
        vals.pop('resident_query', None)
        # Accept typed reporter name when no resident master record was picked.
        contact_name = (vals.get('contact_name') or '').strip()
        if contact_name:
            vals['contact_name'] = contact_name
        elif not vals.get('resident_id'):
            vals.pop('contact_name', None)
        if submit and not vals.get('resident_id') and not vals.get('contact_name'):
            raise UserError(_("Enter a Contact Name, or search and pick a Resident."))
        description = vals.get('description') or ''
        if description and not description.startswith('<'):
            vals['description'] = '<p>%s</p>' % description.replace('\n', '<br/>')
        known = set(Ticket._fields)
        vals = {key: value for key, value in vals.items() if key in known}
        if ticket_id:
            ticket = Ticket.browse(int(ticket_id))
            ticket.write(vals)
        else:
            vals.setdefault('state', 'draft')
            ticket = Ticket.create(vals)
        if files:
            attachment_ids = []
            for upload in files:
                if not upload.get('datas'):
                    continue
                attachment = self.env['ir.attachment'].create({
                    'name': upload.get('name') or _('attachment'),
                    'datas': upload['datas'],
                    'mimetype': upload.get('mimetype') or 'application/octet-stream',
                    'res_model': 'fms.helpdesk.ticket',
                    'res_id': ticket.id,
                })
                attachment_ids.append(attachment.id)
            if attachment_ids:
                ticket.write({'attachment_ids': [(4, att_id) for att_id in attachment_ids]})
        if submit:
            ticket.action_submit()
        else:
            ticket.action_save_draft()
        return {'id': ticket.id, 'name': ticket.name or _('TKT-AUTO'), 'state': ticket.state}

    @api.model
    def save_category(self, vals):
        Category = self.env['fms.helpdesk.category']
        names = vals.pop('subcategory_names', None)
        category_id = vals.pop('id', False)
        if category_id:
            category = Category.browse(int(category_id))
            category.write(vals)
        else:
            category = Category.create(vals)
        if names is not None:
            existing = {s.name.strip().lower(): s for s in category.subcategory_ids}
            keep = set()
            for name in names:
                name = (name or '').strip()
                if not name:
                    continue
                key = name.lower()
                keep.add(key)
                if key not in existing:
                    self.env['fms.helpdesk.subcategory'].create({
                        'name': name, 'category_id': category.id,
                    })
            leftover = category.subcategory_ids.filtered(lambda s: s.name.strip().lower() not in keep)
            leftover.unlink()
        return {'id': category.id}

    @api.model
    def save_routing_rule(self, vals):
        Rule = self.env['fms.helpdesk.routing.rule']
        rule_id = vals.pop('id', False)
        if rule_id:
            rule = Rule.browse(int(rule_id))
            rule.write(vals)
        else:
            rule = Rule.create(vals)
        return {'id': rule.id}

    @api.model
    def save_sla_policy(self, vals):
        Policy = self.env['fms.helpdesk.sla.policy']
        policy_id = vals.pop('id', False)
        if policy_id:
            policy = Policy.browse(int(policy_id))
            policy.write(vals)
        else:
            policy = Policy.create(vals)
        return {'id': policy.id}

    @api.model
    def save_priority(self, vals):
        Priority = self.env['fms.helpdesk.priority']
        Policy = self.env['fms.helpdesk.sla.policy']
        pid = vals.get('id')
        pvals = {
            'name': vals.get('name'),
            'description': vals.get('description') or False,
            'active': vals.get('active', True),
            'escalation_level_id': int(vals['escalation_level_id']) if vals.get('escalation_level_id') else False,
        }
        if pid:
            priority = Priority.browse(int(pid))
            priority.write(pvals)
        else:
            code = (vals.get('code') or vals.get('name') or 'priority').strip().lower().replace(' ', '_')
            pvals['code'] = code
            priority = Priority.create(pvals)
        policy_vals = {
            'response_target': int(vals.get('response_target') or 0) or 1,
            'response_unit': vals.get('response_unit') or 'hours',
            'resolution_target': int(vals.get('resolution_target') or 0) or 1,
            'resolution_unit': vals.get('resolution_unit') or 'hours',
            'escalation_level_id': pvals['escalation_level_id'],
            'priority_id': priority.id,
        }
        policy = Policy.browse(int(vals['policy_id'])) if vals.get('policy_id') else Policy.search(
            [('priority_id', '=', priority.id)], limit=1)
        if policy:
            policy.write(policy_vals)
        else:
            policy_vals['name'] = _('%s Priority SLA', priority.name)
            Policy.create(policy_vals)
        return {'id': priority.id}

    @api.model
    def save_sla_settings(self, vals):
        if not self.env.user.has_group('fms_helpdesk.group_fms_helpdesk_admin'):
            raise UserError(_("Only a Helpdesk Administrator can change SLA settings."))
        ICP = self.env['ir.config_parameter'].sudo()
        at_risk = max(1, min(99, int(vals.get('at_risk') or 80)))
        critical = max(1, min(99, int(vals.get('critical_warning') or 90)))
        ICP.set_param('fms_helpdesk.sla_at_risk_percent', str(at_risk))
        ICP.set_param('fms_helpdesk.sla_critical_warning_percent', str(critical))
        pause_awaiting = bool(vals.get('pause_awaiting'))
        pause_vendor = bool(vals.get('pause_vendor'))
        self.env['fms.helpdesk.sla.policy'].with_context(active_test=False).search([]).write({
            'warning_threshold': at_risk,
            'pause_on_awaiting_resident': pause_awaiting,
            'pause_on_with_vendor': pause_vendor,
        })
        return True

    @api.model
    def simulate_sla(self, ticket_id):
        ticket = self._ticket().browse(int(ticket_id or 0))
        if not ticket.exists():
            raise UserError(_("Select a complaint to simulate SLA timers."))
        ticket._update_sla_status()
        return self._sla_tracker(ticket)

    @api.model
    def test_routing(self, vals):
        vals = vals or {}
        category_id = int(vals.get('category_id') or 0)
        if not category_id:
            raise UserError(_("Select a Category before testing routing."))
        wizard = self.env['fms.helpdesk.routing.test'].create({
            'category_id': category_id,
            'subcategory_id': int(vals.get('subcategory_id') or 0) or False,
            'priority_id': int(vals.get('priority_id') or 0) or False,
        })
        wizard.action_test()
        return {
            'rule': wizard.rule_id.name or '',
            'team': wizard.team_id.name or '',
            'user': wizard.user_id.name or '',
            'sla': wizard.sla_policy_id.name or '',
            'summary': wizard.result_summary or '',
        }

    def _require_admin(self):
        if not self.env.user.has_group('fms_helpdesk.group_fms_helpdesk_admin'):
            raise UserError(_("Only a Helpdesk Administrator can delete Helpdesk records."))

    @api.model
    def delete_ticket(self, ticket_id):
        self._require_admin()
        ticket = self._ticket().browse(int(ticket_id))
        if not ticket.exists():
            raise UserError(_("Ticket not found."))
        name = ticket.name or ticket.title or str(ticket.id)
        ticket.unlink()
        return {'ok': True, 'name': name}

    @api.model
    def delete_team(self, team_id):
        self._require_admin()
        team = self.env['fms.helpdesk.team'].browse(int(team_id))
        if not team.exists():
            raise UserError(_("Support team not found."))
        name = team.name
        team.unlink()
        return {'ok': True, 'name': name}

    @api.model
    def delete_category(self, category_id):
        self._require_admin()
        category = self.env['fms.helpdesk.category'].browse(int(category_id))
        if not category.exists():
            raise UserError(_("Category not found."))
        name = category.name
        category.unlink()
        return {'ok': True, 'name': name}

    @api.model
    def delete_routing_rule(self, rule_id):
        self._require_admin()
        rule = self.env['fms.helpdesk.routing.rule'].browse(int(rule_id))
        if not rule.exists():
            raise UserError(_("Routing rule not found."))
        name = rule.name
        rule.unlink()
        return {'ok': True, 'name': name}

    @api.model
    def delete_sla_policy(self, policy_id):
        self._require_admin()
        policy = self.env['fms.helpdesk.sla.policy'].browse(int(policy_id))
        if not policy.exists():
            raise UserError(_("SLA policy not found."))
        name = policy.name
        policy.unlink()
        return {'ok': True, 'name': name}

    @api.model
    def delete_priority(self, priority_id):
        self._require_admin()
        priority = self.env['fms.helpdesk.priority'].browse(int(priority_id))
        if not priority.exists():
            raise UserError(_("Priority level not found."))
        name = priority.name
        # Prefer archive when still linked; hard-delete when safe.
        linked_tickets = self._ticket().search_count([('priority_id', '=', priority.id)])
        linked_policies = self.env['fms.helpdesk.sla.policy'].search_count([('priority_id', '=', priority.id)])
        if linked_tickets or linked_policies:
            priority.write({'active': False})
            return {'ok': True, 'name': _('%s (archived — still used by tickets/policies)', name), 'archived': True}
        priority.unlink()
        return {'ok': True, 'name': name, 'archived': False}

    @api.model
    def assign_ticket(self, ticket_id, team_id=None, user_id=None, reason=False):
        self._ticket().browse(int(ticket_id)).action_assign(team_id=team_id, user_id=user_id, reason=reason)
        return True

    @api.model
    def escalate_ticket(self, ticket_id, level_id=None, reason='manual', comment=False):
        self._ticket().browse(int(ticket_id)).action_escalate(level_id=level_id, reason=reason, comment=comment)
        return True

    @api.model
    def resolve_ticket(self, ticket_id, description, work_performed=False):
        self._ticket().browse(int(ticket_id)).action_add_resolution(description, work_performed)
        return True

    @api.model
    def close_ticket(self, ticket_id, reason='resolved', comment=False):
        self._ticket().browse(int(ticket_id)).action_close(reason=reason, comment=comment)
        return True

    @api.model
    def reopen_ticket(self, ticket_id, reason):
        self._ticket().browse(int(ticket_id)).action_reopen(reason)
        return True

    @api.model
    def start_progress(self, ticket_id):
        self._ticket().browse(int(ticket_id)).action_start_progress()
        return True

    @api.model
    def verify_resolution(self, ticket_id, remarks=False):
        ticket = self._ticket().browse(int(ticket_id))
        if not ticket.resolution_id:
            raise UserError(_("This complaint has no resolution to verify."))
        ticket.resolution_id.action_verify(remarks)
        return True

    @api.model
    def submit_feedback(self, feedback_id, rating, comment=False):
        feedback = self.env['fms.helpdesk.feedback'].browse(int(feedback_id))
        if not feedback.exists():
            raise UserError(_("Feedback request not found."))
        feedback.write({
            'rating': str(int(rating)),
            'comment': comment or False,
            'state': 'submitted',
        })
        return {'id': feedback.id, 'state': feedback.state, 'rating': feedback.rating_value}

    @api.model
    def save_settings(self, vals):
        if not self.env.user.has_group('fms_helpdesk.group_fms_helpdesk_admin'):
            raise UserError(_("Only a Helpdesk Administrator can change Helpdesk Settings."))
        ICP = self.env['ir.config_parameter'].sudo()
        mapping = {
            'app_name': 'fms_helpdesk.app_name',
            'default_priority_id': 'fms_helpdesk.default_priority_id',
            'auto_routing': 'fms_helpdesk.auto_routing',
            'require_verification': 'fms_helpdesk.require_verification',
            'allow_reopen': 'fms_helpdesk.allow_reopen',
            'reopen_days': 'fms_helpdesk.reopen_days',
            'allow_resident_attachments': 'fms_helpdesk.allow_resident_attachments',
            'allow_multiple_attachments': 'fms_helpdesk.allow_multiple_attachments',
            'feedback_enabled': 'fms_helpdesk.feedback_enabled',
            'low_rating_threshold': 'fms_helpdesk.low_rating_threshold',
        }
        for key, param in mapping.items():
            if key in vals:
                value = vals[key]
                if isinstance(value, bool):
                    value = 'True' if value else 'False'
                ICP.set_param(param, value if value not in (None, False) else '')
        return True
