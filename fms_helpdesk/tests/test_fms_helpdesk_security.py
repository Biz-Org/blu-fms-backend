# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'fms_helpdesk')
class TestFmsHelpdeskSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Ticket = cls.env['fms.helpdesk.ticket']
        cls.viewer = new_test_user(cls.env, login='fms_mgmt', name='Management', groups='fms_helpdesk.group_fms_helpdesk_viewer')
        cls.agent = new_test_user(cls.env, login='fms_sec_agent', name='Agent', groups='fms_helpdesk.group_fms_helpdesk_agent')
        cls.agent_2 = new_test_user(cls.env, login='fms_sec_agent_2', name='Agent Two', groups='fms_helpdesk.group_fms_helpdesk_agent')
        cls.lead = new_test_user(cls.env, login='fms_sec_lead', name='Lead', groups='fms_helpdesk.group_fms_helpdesk_team_lead')
        cls.manager = new_test_user(cls.env, login='fms_sec_manager', name='Facility Manager', groups='fms_helpdesk.group_fms_helpdesk_manager')
        cls.admin_user = new_test_user(cls.env, login='fms_sec_admin', name='Helpdesk Admin', groups='fms_helpdesk.group_fms_helpdesk_admin')
        cls.resident_user = new_test_user(
            cls.env, login='fms_sec_resident', name='Resident One',
            groups='fms_helpdesk.group_fms_helpdesk_resident')
        cls.resident_user.partner_id.write({'fms_is_resident': True, 'email': 'res1@example.com'})
        cls.other_resident = new_test_user(
            cls.env, login='fms_sec_resident_2', name='Resident Two',
            groups='fms_helpdesk.group_fms_helpdesk_resident')
        cls.other_resident.partner_id.write({'fms_is_resident': True, 'email': 'res2@example.com'})

        cls.high = cls.env['fms.helpdesk.priority'].create({
            'name': 'High', 'code': 'high_sec_test', 'sequence': 2, 'is_urgent': True,
        })
        cls.level_1 = cls.env.ref('fms_helpdesk.escalation_level_1')
        cls.team = cls.env['fms.helpdesk.team'].create({
            'name': 'Security Test Team',
            'leader_id': cls.lead.id,
            'member_ids': [(6, 0, [cls.agent.id, cls.agent_2.id])],
        })
        cls.category = cls.env['fms.helpdesk.category'].create({
            'name': 'Security Test Category',
            'default_team_id': cls.team.id,
        })
        cls.subcategory = cls.env['fms.helpdesk.subcategory'].create({
            'name': 'Security Sub',
            'category_id': cls.category.id,
        })

    def _ticket_vals(self, **values):
        vals = {
            'title': 'Security ticket',
            'resident_id': self.resident_user.partner_id.id,
            'category_id': self.category.id,
            'subcategory_id': self.subcategory.id,
            'priority_id': self.high.id,
        }
        vals.update(values)
        return vals

    def _create_as_agent(self, **values):
        return self.Ticket.with_user(self.agent).create(self._ticket_vals(**values))

    def test_management_can_read_but_not_write(self):
        ticket = self._create_as_agent()
        found = self.Ticket.with_user(self.viewer).search([('id', '=', ticket.id)])
        self.assertEqual(found, ticket)
        with self.assertRaises(AccessError):
            ticket.with_user(self.viewer).write({'title': 'Changed'})
        with self.assertRaises(AccessError):
            self.Ticket.with_user(self.viewer).create(self._ticket_vals(title='Viewer create'))

    def test_agent_can_work_ticket_but_not_assign_escalate_close_reopen(self):
        ticket = self._create_as_agent()
        ticket.with_user(self.agent).write({'state': 'in_progress', 'description': '<p>Working</p>'})
        self.env['fms.helpdesk.resolution'].with_user(self.agent).create({
            'ticket_id': ticket.id,
            'description': '<p>Fixed</p>',
        })
        self.assertEqual(ticket.state, 'resolved')

        with self.assertRaises(AccessError):
            ticket.with_user(self.agent).write({'user_id': self.agent_2.id})
        with self.assertRaises(AccessError):
            self.env['fms.helpdesk.escalation'].with_user(self.agent).create({
                'ticket_id': ticket.id, 'level_id': self.level_1.id, 'reason': 'manual',
            })
        with self.assertRaises(AccessError):
            ticket.with_user(self.agent).write({'state': 'closed', 'closure_reason': 'resolved'})

        ticket.with_user(self.lead).write({'state': 'closed', 'closure_reason': 'resolved'})
        with self.assertRaises(AccessError):
            ticket.with_user(self.agent).write({'state': 'reopened', 'last_reopen_reason': 'Again'})

    def test_agent_cannot_verify_resolution(self):
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.require_verification', 'True')
        ticket = self._create_as_agent()
        ticket.with_user(self.agent).write({'state': 'in_progress'})
        resolution = self.env['fms.helpdesk.resolution'].with_user(self.agent).create({
            'ticket_id': ticket.id,
            'description': '<p>Fixed</p>',
        })
        with self.assertRaises(AccessError):
            resolution.with_user(self.agent).action_verify('Looks good')

    def test_team_lead_can_assign_escalate_verify_close_reopen(self):
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.require_verification', 'True')
        ticket = self._create_as_agent()
        ticket.with_user(self.lead).with_context(fms_assignment_reason='Covering').write({'user_id': self.agent_2.id})
        self.assertEqual(ticket.user_id, self.agent_2)

        ticket.with_user(self.agent_2).write({'state': 'in_progress'})
        self.env['fms.helpdesk.escalation'].with_user(self.lead).create({
            'ticket_id': ticket.id, 'level_id': self.level_1.id, 'reason': 'sla_at_risk',
        })
        self.assertEqual(ticket.state, 'escalated')

        resolution = self.env['fms.helpdesk.resolution'].with_user(self.agent).create({
            'ticket_id': ticket.id,
            'description': '<p>Fixed</p>',
        })
        resolution.with_user(self.lead).action_verify('Confirmed')
        self.assertEqual(resolution.state, 'verified')
        ticket.with_user(self.lead).write({'state': 'closed', 'closure_reason': 'resolved'})
        ticket.with_user(self.lead).write({'state': 'reopened', 'last_reopen_reason': 'Leak returned'})
        self.assertEqual(ticket.state, 'reopened')

    def test_facility_manager_cannot_configure_but_can_edit_teams(self):
        with self.assertRaises(AccessError):
            self.category.with_user(self.manager).write({'description': 'hack'})
        with self.assertRaises(AccessError):
            self.env['fms.helpdesk.routing.rule'].with_user(self.manager).create({
                'name': 'Illegal rule',
                'category_id': self.category.id,
                'team_id': self.team.id,
            })
        self.team.with_user(self.manager).write({'description': 'Updated by facility manager'})
        self.assertEqual(self.team.description, 'Updated by facility manager')

    def test_admin_can_configure(self):
        self.category.with_user(self.admin_user).write({'description': 'Admin update'})
        self.assertEqual(self.category.description, 'Admin update')
        rule = self.env['fms.helpdesk.routing.rule'].with_user(self.admin_user).create({
            'name': 'Admin rule',
            'category_id': self.category.id,
            'subcategory_id': self.subcategory.id,
            'team_id': self.team.id,
        })
        self.assertTrue(rule.exists())

    def test_resident_sees_only_own_tickets_and_can_create(self):
        own = self.Ticket.with_user(self.resident_user).create(self._ticket_vals(title='My leak'))
        self.assertTrue(own.name.startswith('HD-'))
        self.assertEqual(own.resident_id, self.resident_user.partner_id)
        other = self._create_as_agent(title='Other leak', resident_id=self.other_resident.partner_id.id)
        ResidentTicket = self.Ticket.with_user(self.resident_user)
        self.assertIn(own, ResidentTicket.search([]))
        self.assertNotIn(other, ResidentTicket.search([]))

        own.with_user(self.resident_user).write({'description': '<p>More photos coming</p>'})
        with self.assertRaises(AccessError):
            own.with_user(self.resident_user).write({'user_id': self.agent.id})
        with self.assertRaises(AccessError):
            own.with_user(self.resident_user).write({'state': 'closed', 'closure_reason': 'resolved'})
        with self.assertRaises(AccessError):
            self.Ticket.with_user(self.resident_user).create(
                self._ticket_vals(resident_id=self.other_resident.partner_id.id, title='For someone else'))

    def test_resident_can_verify_and_submit_feedback(self):
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.require_verification', 'True')
        ticket = self.Ticket.with_user(self.resident_user).create(self._ticket_vals(title='Verify me'))
        ticket.with_user(self.agent).write({'state': 'in_progress'})
        resolution = self.env['fms.helpdesk.resolution'].with_user(self.agent).create({
            'ticket_id': ticket.id,
            'description': '<p>Fixed</p>',
        })
        resolution.with_user(self.resident_user).action_verify('OK from resident')
        self.assertEqual(resolution.state, 'verified')
        ticket.with_user(self.lead).write({'state': 'closed', 'closure_reason': 'resolved'})
        feedback = ticket.feedback_ids
        self.assertEqual(feedback.state, 'pending')
        feedback.with_user(self.resident_user).write({'rating': '5', 'comment': 'Good'})
        self.assertEqual(feedback.state, 'submitted')
        with self.assertRaises(AccessError):
            feedback.with_user(self.agent).write({'state': 'reviewed'})
        feedback.with_user(self.lead).write({'state': 'reviewed', 'review_note': 'Noted'})
        self.assertEqual(feedback.state, 'reviewed')

    def test_agent_cannot_configure_or_delete_tickets(self):
        ticket = self._create_as_agent()
        with self.assertRaises(AccessError):
            self.category.with_user(self.agent).write({'name': 'Hacked'})
        with self.assertRaises(AccessError):
            ticket.with_user(self.agent).unlink()
        with self.assertRaises(AccessError):
            self.team.with_user(self.agent).write({'name': 'Hacked team'})
