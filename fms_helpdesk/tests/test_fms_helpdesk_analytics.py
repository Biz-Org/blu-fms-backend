# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'fms_helpdesk')
class TestFmsHelpdeskAnalytics(TransactionCase):
    """SLA warnings/breaches/escalations + Dashboard/Reports KPIs vs live DB rows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login='fms_analytics_admin', name='Analytics Admin',
            groups='fms_helpdesk.group_fms_helpdesk_admin')
        cls.agent = new_test_user(
            cls.env, login='fms_analytics_agent', name='Analytics Agent',
            groups='fms_helpdesk.group_fms_helpdesk_agent')
        cls.lead = new_test_user(
            cls.env, login='fms_analytics_lead', name='Analytics Lead',
            groups='fms_helpdesk.group_fms_helpdesk_team_lead')
        cls.high = cls.env['fms.helpdesk.priority'].create({
            'name': 'High Analytics', 'code': 'high_analytics', 'sequence': 2, 'is_urgent': True,
        })
        cls.level = cls.env.ref('fms_helpdesk.escalation_level_1')
        cls.team = cls.env['fms.helpdesk.team'].create({
            'name': 'Analytics Team',
            'leader_id': cls.lead.id,
            'member_ids': [(6, 0, [cls.agent.id])],
        })
        cls.category = cls.env['fms.helpdesk.category'].create({
            'name': 'Analytics Plumbing',
            'default_team_id': cls.team.id,
        })
        cls.sub = cls.env['fms.helpdesk.subcategory'].create({
            'name': 'Leak Analytics', 'category_id': cls.category.id,
        })
        cls.policy = cls.env['fms.helpdesk.sla.policy'].create({
            'name': 'Analytics High SLA',
            'priority_id': cls.high.id,
            'category_ids': [(6, 0, cls.category.ids)],
            'response_target': 30,
            'response_unit': 'minutes',
            'resolution_target': 4,
            'resolution_unit': 'hours',
            'coverage': '24x7',
            'warning_threshold': 80,
            'auto_escalate': True,
            'escalation_level_id': cls.level.id,
        })
        cls.env['fms.helpdesk.routing.rule'].create({
            'name': 'Analytics Route',
            'category_id': cls.category.id,
            'subcategory_id': cls.sub.id,
            'priority_id': cls.high.id,
            'team_id': cls.team.id,
            'user_id': cls.agent.id,
            'sla_policy_id': cls.policy.id,
        })
        cls.resident = cls.env['res.partner'].create({
            'name': 'Analytics Resident',
            'fms_is_resident': True,
            'fms_building_name': 'Tower Z',
            'fms_unit_name': 'Z-1',
        })

    def _ticket(self, title='Analytics Leak'):
        ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': title,
            'resident_id': self.resident.id,
            'category_id': self.category.id,
            'subcategory_id': self.sub.id,
            'priority_id': self.high.id,
        })
        self.assertEqual(ticket.sla_status, 'on_track')
        return ticket

    def test_sla_warning_notifies_without_escalating(self):
        ticket = self._ticket('At Risk Notify')
        # Response 30m: keep response on track, push resolution past 80% of 4h (= 192m).
        now = fields.Datetime.now()
        ticket.with_context(fms_internal_write=True).write({
            'sla_start_date': now - timedelta(minutes=200),
            'first_response_date': now - timedelta(minutes=190),
        })
        ticket._update_sla_status()
        self.assertEqual(ticket.resolution_sla_status, 'at_risk')
        self.assertEqual(ticket.sla_status, 'at_risk')
        self.assertFalse(ticket.sla_breached)
        self.assertFalse(ticket.escalation_ids)
        self.assertTrue(ticket.message_ids.filtered(
            lambda m: m.subject and 'At Risk' in (m.subject or '')))
        self.assertTrue(ticket.history_ids.filtered(
            lambda h: h.action == 'sla' and h.new_value == 'At Risk'))

    def test_sla_breach_cron_escalates_and_notifies(self):
        ticket = self._ticket('Breach Escalate')
        ticket.with_context(fms_internal_write=True).write({
            'sla_start_date': fields.Datetime.now() - timedelta(hours=5),
        })
        count = self.env['fms.helpdesk.ticket']._cron_update_sla_status()
        self.assertGreaterEqual(count, 1)
        ticket.invalidate_recordset()
        self.assertTrue(ticket.sla_breached)
        self.assertEqual(ticket.sla_status, 'breached')
        self.assertEqual(len(ticket.escalation_ids), 1)
        escalation = ticket.escalation_ids
        self.assertEqual(escalation.trigger_type, 'automatic')
        self.assertEqual(escalation.reason, 'sla_breached')
        self.assertEqual(ticket.state, 'escalated')
        self.assertTrue(ticket.message_ids.filtered(
            lambda m: m.subject and ('Breached' in (m.subject or '') or 'Escalation' in (m.subject or ''))))
        self.assertTrue(ticket.history_ids.filtered(lambda h: h.action == 'escalation'))

    def test_dashboard_totals_match_database(self):
        open_ticket = self._ticket('Dash Open')
        resolved = self._ticket('Dash Resolved')
        resolved.with_user(self.agent).write({'state': 'in_progress'})
        self.env['fms.helpdesk.resolution'].with_user(self.agent).create({
            'ticket_id': resolved.id,
            'description': '<p>Fixed</p>',
            'work_performed': 'Repaired',
        })
        resolved.invalidate_recordset()
        self.assertIn(resolved.state, ('resolved', 'awaiting_verification'))

        Ticket = self.env['fms.helpdesk.ticket']
        base = [('state', '!=', 'draft')]
        expected = {
            'total': Ticket.search_count(base),
            'open': Ticket.search_count(base + [('state', 'in', ('new', 'open', 'assigned'))]),
            'in_progress': Ticket.search_count(base + [('state', '=', 'in_progress')]),
            'resolved': Ticket.search_count(base + [('state', 'in', ('resolved', 'awaiting_verification', 'closed'))]),
            'breached': Ticket.search_count(base + [('sla_breached', '=', True), ('state', 'not in', ('closed', 'draft'))]),
            'unassigned': Ticket.search_count(base + [
                ('is_unassigned', '=', True),
                ('state', 'in', ('new', 'open', 'assigned', 'in_progress', 'pending',
                                 'awaiting_resident', 'with_vendor', 'escalated')),
            ]),
            'escalated': Ticket.search_count(base + [('is_escalated', '=', True)]),
        }
        Ui = self.env['fms.helpdesk.ui'].with_user(self.admin)
        dash = Ui.load_screen('dashboard', {})
        for key, value in expected.items():
            self.assertEqual(dash['kpis'][key], value, key)
        self.assertTrue(any(row['id'] == open_ticket.id for row in dash['recent']))
        self.assertIn('activity', dash)
        self.assertIn('sla', dash)
        self.assertEqual(
            dash['sla']['compliance'],
            Ui._sla_breakdown(Ticket.search(base))['compliance'],
        )

    def test_reports_kpis_filters_and_export_match_db(self):
        t1 = self._ticket('Report A')
        t2 = self._ticket('Report B')
        t2.with_context(fms_internal_write=True).write({
            'sla_start_date': fields.Datetime.now() - timedelta(hours=5),
        })
        t2._update_sla_status()
        self.assertTrue(t2.sla_breached)

        Ui = self.env['fms.helpdesk.ui'].with_user(self.admin)
        Ticket = self.env['fms.helpdesk.ticket']
        reports = Ui.load_screen('reports', {'category_id': self.category.id})
        domain = [
            ('state', '!=', 'draft'),
            ('category_id', '=', self.category.id),
        ]
        tickets = Ticket.search(domain)
        self.assertEqual(reports['kpis']['total'], len(tickets))
        self.assertEqual(
            reports['kpis']['breached'],
            len(tickets.filtered(lambda t: t.sla_breached)),
        )
        self.assertEqual(
            reports['kpis']['compliance'],
            Ui._sla_breakdown(tickets)['compliance'],
        )
        self.assertTrue(any(row['id'] == self.category.id for row in reports['by_category']))
        self.assertTrue(any(tm['id'] == self.team.id for tm in reports['teams']))
        self.assertEqual(len(reports['volume']), 14)

        breached = Ui.load_screen('reports', {
            'category_id': self.category.id,
            'sla_status': 'breached',
        })
        self.assertEqual(
            breached['kpis']['total'],
            Ticket.search_count(domain + [('sla_breached', '=', True)]),
        )
        self.assertGreaterEqual(breached['kpis']['total'], 1)

        export_rows = Ui.export_report_rows({'category_id': self.category.id})
        self.assertTrue(any(r['name'] == t1.name for r in export_rows))
        self.assertTrue(any(r['name'] == t2.name and r['sla_breached'] == 'yes' for r in export_rows))

        # Shared SLA math: dashboard and reports on the same ticket set stay consistent.
        all_tickets = Ticket.search([('state', '!=', 'draft')])
        shared = Ui._sla_breakdown(all_tickets)
        dash = Ui.load_screen('dashboard', {})
        all_reports = Ui.load_screen('reports', {})
        self.assertEqual(dash['sla']['compliance'], shared['compliance'])
        self.assertEqual(all_reports['kpis']['compliance'], shared['compliance'])
        self.assertEqual(all_reports['sla']['counts']['breached'], shared['breached'])
