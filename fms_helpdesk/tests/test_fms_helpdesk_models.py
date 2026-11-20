# -*- coding: utf-8 -*-

import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'fms_helpdesk')
class TestFmsHelpdeskModels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        agent_group = 'fms_helpdesk.group_fms_helpdesk_agent'
        cls.agent_1 = new_test_user(cls.env, login='fms_agent_1', name='Rahul Patil', groups=agent_group)
        cls.agent_2 = new_test_user(cls.env, login='fms_agent_2', name='Amit Shah', groups=agent_group)
        cls.lead = new_test_user(
            cls.env, login='fms_lead', name='Team Lead', groups='fms_helpdesk.group_fms_helpdesk_team_lead')

        cls.high = cls.env['fms.helpdesk.priority'].create({
            'name': 'High', 'code': 'high_model_test', 'sequence': 2, 'is_urgent': True,
        })
        cls.medium = cls.env['fms.helpdesk.priority'].create({
            'name': 'Medium', 'code': 'medium_model_test', 'sequence': 3,
        })
        cls.level_1 = cls.env.ref('fms_helpdesk.escalation_level_1')

        cls.team = cls.env['fms.helpdesk.team'].create({
            'name': 'Plumbing Team (test)',
            'leader_id': cls.lead.id,
            'member_ids': [(6, 0, [cls.agent_1.id, cls.agent_2.id])],
            'assignment_method': 'round_robin',
        })
        cls.category = cls.env['fms.helpdesk.category'].create({
            'name': 'Plumbing (test)',
            'default_team_id': cls.team.id,
        })
        cls.leak = cls.env['fms.helpdesk.subcategory'].create({'name': 'Water Leakage', 'category_id': cls.category.id})
        cls.drain = cls.env['fms.helpdesk.subcategory'].create({'name': 'Drain Blockage', 'category_id': cls.category.id})
        cls.sla_high = cls.env['fms.helpdesk.sla.policy'].create({
            'name': 'High Priority 24x7 (test)',
            'priority_id': cls.high.id,
            'category_ids': [(6, 0, cls.category.ids)],
            'response_target': 30,
            'response_unit': 'minutes',
            'resolution_target': 4,
            'resolution_unit': 'hours',
            'coverage': '24x7',
        })
        cls.sla_medium = cls.env['fms.helpdesk.sla.policy'].create({
            'name': 'Medium SLA (test)',
            'priority_id': cls.medium.id,
            'response_target': 2,
            'response_unit': 'hours',
            'resolution_target': 8,
            'resolution_unit': 'hours',
        })
        cls.rule = cls.env['fms.helpdesk.routing.rule'].create({
            'name': 'Water Leakage Rule',
            'category_id': cls.category.id,
            'subcategory_id': cls.leak.id,
            'priority_id': cls.high.id,
            'team_id': cls.team.id,
            'user_id': cls.agent_1.id,
            'sla_policy_id': cls.sla_high.id,
        })
        cls.resident = cls.env['res.partner'].create({
            'name': 'A. Sharma',
            'email': 'a.sharma@example.com',
            'fms_is_resident': True,
            'fms_building_name': 'Tower A',
            'fms_unit_name': 'A-1204',
        })

    def _create_ticket(self, **values):
        vals = {
            'title': 'Water Leakage in Apartment',
            'resident_id': self.resident.id,
            'category_id': self.category.id,
            'subcategory_id': self.leak.id,
            'priority_id': self.high.id,
        }
        vals.update(values)
        return self.env['fms.helpdesk.ticket'].with_user(self.agent_1).create(vals)

    def _resolve_and_close(self, ticket):
        ticket.with_user(self.agent_1).write({'state': 'in_progress'})
        self.env['fms.helpdesk.resolution'].with_user(self.agent_1).create({
            'ticket_id': ticket.id,
            'description': '<p>Pipe joint replaced</p>',
            'work_performed': 'Replaced joint and tested for leaks',
        })
        ticket.with_user(self.lead).write({
            'state': 'closed', 'closure_reason': 'resolved', 'closure_comment': 'Resident confirmed',
        })

    def test_all_models_registered(self):
        for model in (
            'fms.helpdesk.ticket', 'fms.helpdesk.ticket.history', 'fms.helpdesk.assignment',
            'fms.helpdesk.team', 'fms.helpdesk.priority', 'fms.helpdesk.category', 'fms.helpdesk.subcategory',
            'fms.helpdesk.routing.rule', 'fms.helpdesk.sla.policy', 'fms.helpdesk.escalation.level',
            'fms.helpdesk.escalation', 'fms.helpdesk.resolution', 'fms.helpdesk.feedback',
        ):
            self.assertIn(model, self.env.registry, model)
        self.assertIn('fms_is_resident', self.env['res.partner']._fields)

    def test_submission_numbers_routes_and_starts_sla(self):
        ticket = self._create_ticket()
        self.assertRegex(ticket.name, r'^HD-\d{4,}$')
        self.assertEqual(ticket.routing_rule_id, self.rule)
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.user_id, self.agent_1)
        self.assertEqual(ticket.state, 'assigned')
        self.assertEqual(ticket.sla_policy_id, self.sla_high)
        self.assertEqual(ticket.response_deadline, ticket.sla_start_date + timedelta(minutes=30))
        self.assertEqual(ticket.resolution_deadline, ticket.sla_start_date + timedelta(hours=4))
        self.assertEqual(ticket.sla_status, 'on_track')
        self.assertEqual((ticket.building_name, ticket.unit_name), ('Tower A', 'A-1204'))
        self.assertEqual(ticket.contact_email, 'a.sharma@example.com')
        self.assertNotEqual(self._create_ticket(title='Second').name, ticket.name)

    def test_draft_gets_number_only_on_submit(self):
        draft = self._create_ticket(state='draft', category_id=False, subcategory_id=False)
        self.assertFalse(draft.name)
        self.assertFalse(draft.sla_start_date)
        with self.assertRaises(ValidationError):
            draft.action_submit()
        draft.write({'category_id': self.category.id, 'subcategory_id': self.leak.id})
        draft.action_submit()
        self.assertTrue(draft.name.startswith('HD-'))
        self.assertEqual(draft.state, 'assigned')

    def test_category_default_team_uses_round_robin(self):
        first = self._create_ticket(subcategory_id=self.drain.id, priority_id=self.medium.id)
        second = self._create_ticket(subcategory_id=self.drain.id, priority_id=self.medium.id)
        self.assertFalse(first.routing_rule_id)
        self.assertEqual(first.team_id, self.team)
        self.assertEqual(first.user_id | second.user_id, self.agent_1 | self.agent_2)
        self.assertEqual(first.sla_policy_id, self.sla_medium)

    def test_subcategory_must_belong_to_category(self):
        electrical = self.env['fms.helpdesk.category'].create({'name': 'Electrical (test)'})
        with self.assertRaises(ValidationError):
            self._create_ticket(category_id=electrical.id)

    def test_invalid_status_transition_is_blocked(self):
        ticket = self._create_ticket()
        with self.assertRaises(UserError):
            ticket.with_user(self.lead).write({'state': 'closed', 'closure_reason': 'resolved'})

    def test_sla_at_risk_then_breached(self):
        ticket = self._create_ticket()
        now = fields.Datetime.now()
        ticket.with_context(fms_internal_write=True).write({'sla_start_date': now - timedelta(minutes=200)})
        ticket._update_sla_status()
        self.assertEqual(ticket.response_sla_status, 'breached')
        self.assertEqual(ticket.resolution_sla_status, 'at_risk')
        self.assertEqual(ticket.sla_status, 'breached')

        ticket.with_context(fms_internal_write=True).write({'sla_start_date': now - timedelta(hours=5)})
        self.env['fms.helpdesk.ticket']._cron_update_sla_status()
        self.assertEqual(ticket.resolution_sla_status, 'breached')
        self.assertTrue(ticket.sla_breached)
        self.assertTrue(ticket.history_ids.filtered(lambda h: h.action == 'sla' and h.new_value == 'Breached'))

    def test_waiting_state_does_not_count_as_first_response(self):
        ticket = self._create_ticket()
        ticket.write({'state': 'awaiting_resident'})
        self.assertFalse(
            ticket.first_response_date,
            'Awaiting Resident must not complete the response SLA',
        )
        ticket.write({'state': 'in_progress'})
        self.assertTrue(ticket.first_response_date)

    def test_waiting_state_pauses_and_extends_sla(self):
        ticket = self._create_ticket()
        ticket.write({'state': 'in_progress'})
        ticket.write({'state': 'awaiting_resident'})
        self.assertEqual(ticket.resolution_sla_status, 'paused')
        deadline_before = ticket.resolution_deadline
        ticket.with_context(fms_internal_write=True).write(
            {'sla_paused_since': fields.Datetime.now() - timedelta(minutes=90)})
        ticket.write({'state': 'in_progress'})
        self.assertFalse(ticket.sla_paused_since)
        self.assertAlmostEqual(ticket.sla_paused_minutes, 90, delta=1)
        extension = (ticket.resolution_deadline - deadline_before).total_seconds() / 60
        self.assertAlmostEqual(extension, 90, delta=1)
        self.assertEqual(ticket.resolution_sla_status, 'on_track')

    def test_closure_requires_resolution_and_requests_feedback(self):
        ticket = self._create_ticket()
        ticket.with_user(self.agent_1).write({'state': 'in_progress'})
        ticket.with_user(self.agent_1).write({'state': 'resolved'})
        with self.assertRaises(AccessError):
            ticket.with_user(self.agent_1).write({'state': 'closed', 'closure_reason': 'resolved'})
        with self.assertRaises(ValidationError):
            ticket.with_user(self.lead).write({'state': 'closed', 'closure_reason': 'resolved'})

        self._resolve_and_close(self._create_ticket(title='Closable'))
        closed = self.env['fms.helpdesk.ticket'].search([('title', '=', 'Closable')])
        self.assertEqual(closed.state, 'closed')
        self.assertTrue(closed.closed_date)
        self.assertEqual(closed.resolved_by_id, self.agent_1)
        self.assertEqual(closed.resolution_sla_status, 'completed')

        feedback = closed.feedback_ids
        self.assertEqual(feedback.state, 'pending')
        feedback.write({'rating': '2', 'comment': 'Took too long'})
        self.assertEqual(feedback.state, 'submitted')
        self.assertTrue(feedback.is_low_rating)
        self.assertEqual(closed.rating, 2)

    def test_reopen_requires_reason(self):
        ticket = self._create_ticket()
        self._resolve_and_close(ticket)
        with self.assertRaises(ValidationError):
            ticket.with_user(self.lead).write({'state': 'reopened'})
        ticket.with_user(self.lead).write({'state': 'reopened', 'last_reopen_reason': 'Leak started again'})
        self.assertEqual(ticket.reopen_count, 1)
        self.assertFalse(ticket.closed_date)
        self.assertTrue(ticket.history_ids.filtered(
            lambda h: h.action == 'reopen' and h.remarks == 'Leak started again'))

    def test_reassignment_history_and_protected_audit_trail(self):
        ticket = self._create_ticket()
        ticket.with_user(self.lead).with_context(fms_assignment_reason='Workload balancing').write({'user_id': self.agent_2.id})
        reassign = ticket.assignment_ids.filtered(lambda a: a.assignment_type == 'reassign')
        self.assertEqual(reassign.previous_user_id, self.agent_1)
        self.assertEqual(reassign.reason, 'Workload balancing')
        self.assertEqual(ticket.reassignment_count, 1)
        self.assertTrue({'create', 'submit', 'status', 'assignment'} <= set(ticket.history_ids.mapped('action')))

        line = ticket.history_ids[:1]
        with self.assertRaises(UserError):
            line.write({'remarks': 'tampered'})
        with self.assertRaises(UserError):
            line.with_user(self.lead).unlink()
        with self.assertRaises(UserError):
            reassign.write({'reason': 'tampered'})

    def test_reassign_reason_required_when_configured(self):
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.reassign_reason_required', 'True')
        ticket = self._create_ticket()
        with self.assertRaises(UserError):
            ticket.with_user(self.lead).write({'user_id': self.agent_2.id})
        ticket.with_user(self.lead).with_context(fms_assignment_reason='Agent on leave').write({'user_id': self.agent_2.id})
        self.assertEqual(ticket.user_id, self.agent_2)

    def test_escalation_lifecycle(self):
        ticket = self._create_ticket()
        ticket.write({'state': 'in_progress'})
        Escalation = self.env['fms.helpdesk.escalation'].with_user(self.lead)
        escalation = Escalation.create({'ticket_id': ticket.id, 'level_id': self.level_1.id, 'reason': 'sla_at_risk'})
        self.assertEqual(escalation.owner_id, self.lead)
        self.assertEqual(ticket.state, 'escalated')
        self.assertEqual(ticket.escalation_level_id, self.level_1)
        with self.assertRaises(ValidationError):
            Escalation.create({'ticket_id': ticket.id, 'level_id': self.level_1.id, 'reason': 'manual'})

        escalation.write({'state': 'resolved', 'resolution_note': 'Plumber dispatched'})
        self.assertTrue(escalation.resolved_date)
        self.assertFalse(ticket.is_escalated)
        self.assertEqual(ticket.state, 'in_progress')

    def test_unassigned_when_no_team_can_be_routed(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Unrouted (test)', 'auto_routing': False,
        })
        ticket = self._create_ticket(category_id=category.id, subcategory_id=False, priority_id=self.medium.id)
        self.assertEqual(ticket.state, 'new')
        self.assertFalse(ticket.team_id)
        self.assertFalse(ticket.user_id)
        self.assertTrue(ticket.is_unassigned)
        ticket.with_user(self.lead).action_assign(team_id=self.team.id, user_id=self.agent_2.id, reason='Manual queue pickup')
        self.assertEqual(ticket.state, 'assigned')
        self.assertEqual(ticket.user_id, self.agent_2)

    def test_first_matching_routing_rule_wins(self):
        earlier = self.env['fms.helpdesk.routing.rule'].create({
            'name': 'Earlier leak rule',
            'sequence': 1,
            'category_id': self.category.id,
            'subcategory_id': self.leak.id,
            'priority_id': self.high.id,
            'team_id': self.team.id,
            'user_id': self.agent_2.id,
            'sla_policy_id': self.sla_high.id,
        })
        ticket = self._create_ticket(title='Ordered route')
        self.assertEqual(ticket.routing_rule_id, earlier)
        self.assertEqual(ticket.user_id, self.agent_2)

    def test_waiting_state_does_not_pause_when_disabled(self):
        self.sla_high.write({'pause_on_awaiting_resident': False})
        ticket = self._create_ticket(title='No pause')
        ticket.write({'state': 'in_progress'})
        ticket.write({'state': 'awaiting_resident'})
        self.assertNotEqual(ticket.resolution_sla_status, 'paused')
        self.assertFalse(ticket.sla_paused_since)

    def test_sla_breach_escalates_only_when_policy_says_so(self):
        quiet = self._create_ticket(title='Breach without auto')
        quiet.with_context(fms_internal_write=True).write({'sla_start_date': fields.Datetime.now() - timedelta(hours=5)})
        quiet._update_sla_status()
        self.assertTrue(quiet.sla_breached)
        self.assertFalse(quiet.escalation_ids)

        self.sla_high.write({'auto_escalate': True, 'escalation_level_id': self.level_1.id})
        ticket = self._create_ticket(title='Breach with auto')
        ticket.write({'state': 'in_progress'})
        ticket.with_context(fms_internal_write=True).write({'sla_start_date': fields.Datetime.now() - timedelta(hours=5)})
        ticket._update_sla_status()
        self.assertEqual(ticket.state, 'escalated')
        escalation = ticket.escalation_ids
        self.assertEqual(escalation.trigger_type, 'automatic')
        self.assertEqual(escalation.reason, 'sla_breached')
        self.assertEqual(escalation.level_id, self.level_1)
        ticket._update_sla_status()
        self.assertEqual(len(ticket.escalation_ids), 1)

    def test_verification_is_required_before_closure_when_configured(self):
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.require_verification', 'True')
        ticket = self._create_ticket(title='Needs verify')
        ticket.write({'state': 'in_progress'})
        resolution = ticket.with_user(self.agent_1).action_add_resolution('Joint replaced', 'Pressure test passed')
        self.assertEqual(ticket.state, 'awaiting_verification')
        with self.assertRaises(ValidationError):
            ticket.with_user(self.lead).action_close('resolved', 'Too soon')
        resolution.with_user(self.lead).action_verify('Confirmed on site')
        self.assertEqual(resolution.state, 'verified')
        ticket.with_user(self.lead).action_close('resolved', 'Verified and closed')
        self.assertEqual(ticket.state, 'closed')

    def test_reopen_window_and_feedback_switch(self):
        ticket = self._create_ticket(title='Window')
        self._resolve_and_close(ticket)
        ticket.with_context(fms_internal_write=True).write({'closed_date': fields.Datetime.now() - timedelta(days=8)})
        with self.assertRaises(UserError):
            ticket.with_user(self.lead).action_reopen('Too late')

        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.feedback_enabled', 'False')
        silent = self._create_ticket(title='No feedback')
        self._resolve_and_close(silent)
        self.assertFalse(silent.feedback_ids)
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.feedback_enabled', 'True')

    def test_empty_resolution_is_rejected(self):
        ticket = self._create_ticket(title='Empty resolution')
        ticket.write({'state': 'in_progress'})
        with self.assertRaises(UserError):
            ticket.action_add_resolution('   ')

    def test_attachment_type_is_validated(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'tool.exe',
            'datas': base64.b64encode(b'not an image'),
        })
        with self.assertRaises(ValidationError):
            self._create_ticket(attachment_ids=[(6, 0, attachment.ids)])
