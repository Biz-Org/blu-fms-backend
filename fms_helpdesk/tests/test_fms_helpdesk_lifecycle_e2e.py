# -*- coding: utf-8 -*-

"""End-to-end complaint lifecycle: create → route → work → resolve → close → feedback."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'fms_helpdesk')
class TestFmsHelpdeskLifecycleE2E(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = new_test_user(
            cls.env, login='fms_e2e_agent', name='E2E Agent',
            groups='fms_helpdesk.group_fms_helpdesk_agent')
        cls.lead = new_test_user(
            cls.env, login='fms_e2e_lead', name='E2E Lead',
            groups='fms_helpdesk.group_fms_helpdesk_team_lead')
        cls.resident_user = new_test_user(
            cls.env, login='fms_e2e_resident', name='E2E Resident',
            groups='base.group_portal,fms_helpdesk.group_fms_helpdesk_resident')
        cls.resident_user.partner_id.write({
            'fms_is_resident': True,
            'fms_building_name': 'Tower E2E',
            'fms_unit_name': 'E-101',
        })
        cls.high = cls.env['fms.helpdesk.priority'].create({
            'name': 'E2E High', 'code': 'e2e_high', 'sequence': 2, 'is_urgent': True,
        })
        cls.level = cls.env.ref('fms_helpdesk.escalation_level_1')
        cls.team = cls.env['fms.helpdesk.team'].create({
            'name': 'E2E Team',
            'leader_id': cls.lead.id,
            'member_ids': [(6, 0, [cls.agent.id])],
        })
        cls.category = cls.env['fms.helpdesk.category'].create({
            'name': 'E2E Plumbing',
            'default_team_id': cls.team.id,
        })
        cls.sub = cls.env['fms.helpdesk.subcategory'].create({
            'name': 'E2E Leak', 'category_id': cls.category.id,
        })
        cls.policy = cls.env['fms.helpdesk.sla.policy'].create({
            'name': 'E2E SLA',
            'priority_id': cls.high.id,
            'category_ids': [(6, 0, cls.category.ids)],
            'response_target': 30,
            'response_unit': 'minutes',
            'resolution_target': 4,
            'resolution_unit': 'hours',
            'coverage': '24x7',
            'auto_escalate': True,
            'escalation_level_id': cls.level.id,
        })
        cls.env['fms.helpdesk.routing.rule'].create({
            'name': 'E2E Route',
            'category_id': cls.category.id,
            'subcategory_id': cls.sub.id,
            'priority_id': cls.high.id,
            'team_id': cls.team.id,
            'user_id': cls.agent.id,
            'sla_policy_id': cls.policy.id,
        })

    def test_full_lifecycle_create_to_feedback(self):
        Ticket = self.env['fms.helpdesk.ticket']
        Ui = self.env['fms.helpdesk.ui']

        # 1) Create + submit (routing, SLA, urgent notify)
        ticket = Ticket.with_user(self.agent).create({
            'title': 'E2E Kitchen Leak',
            'description': '<p>Water under sink</p>',
            'resident_id': self.resident_user.partner_id.id,
            'category_id': self.category.id,
            'subcategory_id': self.sub.id,
            'priority_id': self.high.id,
        })
        self.assertTrue(ticket.name.startswith('HD-'))
        self.assertEqual(ticket.state, 'assigned')
        self.assertEqual(ticket.user_id, self.agent)
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.sla_policy_id, self.policy)
        self.assertEqual(ticket.sla_status, 'on_track')
        self.assertTrue(ticket.message_ids.filtered(
            lambda m: m.subject and 'High/Critical' in (m.subject or '')))

        # 2) Work + resolve
        ticket.with_user(self.agent).action_start_progress()
        self.assertEqual(ticket.state, 'in_progress')
        self.assertTrue(ticket.first_response_date)
        Ui.with_user(self.agent).resolve_ticket(ticket.id, 'Joint replaced', 'Pressure tested')
        ticket.invalidate_recordset()
        self.assertIn(ticket.state, ('resolved', 'awaiting_verification'))

        # 3) Close → feedback pending
        Ui.with_user(self.lead).close_ticket(ticket.id, 'resolved', 'Resident confirmed')
        ticket.invalidate_recordset()
        self.assertEqual(ticket.state, 'closed')
        feedback = ticket.feedback_ids
        self.assertEqual(len(feedback), 1)
        self.assertEqual(feedback.state, 'pending')

        # 4) Resident submits feedback via UI RPC
        result = Ui.with_user(self.resident_user).submit_feedback(feedback.id, 5, 'Fixed quickly')
        self.assertEqual(result['state'], 'submitted')
        self.assertEqual(result['rating'], 5)
        feedback.invalidate_recordset()
        self.assertEqual(feedback.state, 'submitted')
        self.assertEqual(feedback.rating_value, 5)

        # 5) Dashboard / reports see the closed ticket (permission-aware, live DB)
        dash = Ui.with_user(self.lead).load_screen('dashboard', {})
        self.assertGreaterEqual(dash['kpis']['total'], 1)
        self.assertGreaterEqual(dash['kpis']['resolved'], 1)
        reports = Ui.with_user(self.lead).load_screen('reports', {'category_id': self.category.id})
        self.assertGreaterEqual(reports['kpis']['total'], 1)
        self.assertTrue(any(row['name'] == ticket.name for row in reports['export_rows']))

        # 6) Audit trail covers submit → feedback
        actions = set(ticket.history_ids.mapped('action'))
        self.assertTrue({'submit', 'status', 'resolution', 'feedback'} & actions)

    def test_ui_feedback_screen_lists_pending_after_close(self):
        ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': 'E2E Feedback List',
            'resident_id': self.resident_user.partner_id.id,
            'category_id': self.category.id,
            'subcategory_id': self.sub.id,
            'priority_id': self.high.id,
        })
        ticket.with_user(self.agent).action_start_progress()
        self.env['fms.helpdesk.ui'].with_user(self.agent).resolve_ticket(
            ticket.id, 'Done', 'Checked')
        self.env['fms.helpdesk.ui'].with_user(self.lead).close_ticket(ticket.id, 'resolved', False)
        screen = self.env['fms.helpdesk.ui'].with_user(self.lead).load_screen('feedback', {'tab': 'pending'})
        self.assertGreaterEqual(screen['kpis']['pending'], 1)
        self.assertTrue(any(row['ticket_id'] == ticket.id for row in screen['rows']))
