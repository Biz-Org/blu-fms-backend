# -*- coding: utf-8 -*-

from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'fms_helpdesk')
class TestFmsHelpdeskUi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = new_test_user(
            cls.env, login='fms_ui_admin', name='UI Admin',
            groups='fms_helpdesk.group_fms_helpdesk_admin')
        cls.agent = new_test_user(
            cls.env, login='fms_ui_agent', name='UI Agent',
            groups='fms_helpdesk.group_fms_helpdesk_agent')
        cls.high = cls.env['fms.helpdesk.priority'].create({
            'name': 'High', 'code': 'high_ui_test', 'sequence': 2, 'is_urgent': True,
        })
        cls.low = cls.env['fms.helpdesk.priority'].create({
            'name': 'Low', 'code': 'low_ui_test', 'sequence': 4,
        })
        cls.env['fms.helpdesk.sla.policy'].create({
            'name': 'High SLA UI',
            'priority_id': cls.high.id,
            'response_target': 30,
            'response_unit': 'minutes',
            'resolution_target': 4,
            'resolution_unit': 'hours',
        })
        cls.team = cls.env['fms.helpdesk.team'].create({
            'name': 'UI Plumbing Team',
            'member_ids': [(6, 0, [cls.agent.id])],
        })
        cls.resident = cls.env['res.partner'].create({
            'name': 'UI Resident',
            'fms_is_resident': True,
            'fms_building_name': 'Tower A',
            'fms_unit_name': 'A-101',
        })

    def test_category_form_creates_real_subcategories(self):
        Category = self.env['fms.helpdesk.category'].with_user(self.admin_user)
        with Form(Category) as form:
            form.name = 'Plumbing UI'
            form.description = 'Water supply and leakage'
            form.default_team_id = self.team
            form.active = True
            with form.subcategory_ids.new() as line:
                line.name = 'Water Leakage'
            with form.subcategory_ids.new() as line:
                line.name = 'Drain Blockage'
        category = Category.search([('name', '=', 'Plumbing UI')], limit=1)
        self.assertTrue(category)
        self.assertEqual(len(category.subcategory_ids), 2)
        self.assertEqual(category.default_team_id, self.team)
        self.assertIn('2 subcat', category.subcategory_summary)

    def test_test_routing_uses_real_rules(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Electrical UI',
            'default_team_id': self.team.id,
        })
        sub = self.env['fms.helpdesk.subcategory'].create({
            'name': 'Short Circuit',
            'category_id': category.id,
        })
        rule = self.env['fms.helpdesk.routing.rule'].create({
            'name': 'Electrical High Rule',
            'category_id': category.id,
            'subcategory_id': sub.id,
            'priority_id': self.high.id,
            'team_id': self.team.id,
            'user_id': self.agent.id,
            'sla_policy_id': self.env['fms.helpdesk.sla.policy'].search([('priority_id', '=', self.high.id)], limit=1).id,
        })
        wizard = self.env['fms.helpdesk.routing.test'].with_user(self.admin_user).create({
            'category_id': category.id,
            'subcategory_id': sub.id,
            'priority_id': self.high.id,
        })
        wizard.action_test()
        self.assertEqual(wizard.rule_id, rule)
        self.assertEqual(wizard.team_id, self.team)
        self.assertEqual(wizard.user_id, self.agent)
        self.assertTrue(wizard.result_summary)

    def test_create_ticket_form_draft_then_submit(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'HVAC UI',
            'default_team_id': self.team.id,
        })
        sub = self.env['fms.helpdesk.subcategory'].create({
            'name': 'AC Not Cooling',
            'category_id': category.id,
        })
        Ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).with_context(default_state='draft')
        with Form(Ticket) as form:
            form.title = 'AC Not Cooling'
            form.resident_id = self.resident
            form.category_id = category
            form.subcategory_id = sub
            form.priority_id = self.high
            form.description = '<p>Unit running but not cooling.</p>'
        ticket = Ticket.search([('title', '=', 'AC Not Cooling')], limit=1)
        self.assertEqual(ticket.state, 'draft')
        self.assertFalse(ticket.name)
        self.assertEqual(ticket.building_name, 'Tower A')
        self.assertEqual(ticket.unit_name, 'A-101')
        ticket.action_submit()
        self.assertTrue(ticket.name.startswith('HD-'))
        self.assertNotEqual(ticket.state, 'draft')
        self.assertEqual(ticket.team_id, self.team)

    def test_complaints_list_reads_database_tickets(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Housekeeping UI',
            'default_team_id': self.team.id,
        })
        ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': 'Cleaning Request',
            'resident_id': self.resident.id,
            'category_id': category.id,
            'priority_id': self.low.id,
        })
        found = self.env['fms.helpdesk.ticket'].with_user(self.agent).search([('id', '=', ticket.id)])
        self.assertEqual(found.title, 'Cleaning Request')
        self.assertTrue(found.preview_ticket_label)
        action = self.env.ref('fms_helpdesk.action_fms_helpdesk_ticket')
        self.assertEqual(action.res_model, 'fms.helpdesk.ticket')
        self.assertIn('list', action.view_mode)
        self.assertIn('form', action.view_mode)

    def test_ui_api_reads_live_records_not_placeholders(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Plumbing Live',
            'default_team_id': self.team.id,
            'description': 'Water supply, leakage and plumbing-related complaints.',
        })
        self.env['fms.helpdesk.subcategory'].create({
            'name': 'Water Leakage', 'category_id': category.id,
        })
        ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': 'Water Leakage',
            'resident_id': self.resident.id,
            'category_id': category.id,
            'priority_id': self.high.id,
        })
        ticket.action_submit()
        Ui = self.env['fms.helpdesk.ui'].with_user(self.admin_user)
        dashboard = Ui.load_screen('dashboard', {})
        self.assertGreaterEqual(dashboard['kpis']['total'], 1)
        self.assertTrue(any(row['title'] == 'Water Leakage' for row in dashboard['recent']))
        complaints = Ui.load_screen('complaints', {'search': 'Water Leakage'})
        self.assertTrue(any(row['id'] == ticket.id for row in complaints['tickets']))
        categories = Ui.load_screen('categories', {})
        self.assertTrue(any(row['name'] == 'Plumbing Live' for row in categories['categories']))
        created = Ui.with_user(self.agent).save_ticket({
            'title': 'Lift Not Working',
            'resident_id': self.resident.id,
            'category_id': category.id,
            'priority_id': self.high.id,
            'description': 'Lift stuck on floor 2',
        }, True)
        self.assertTrue(created['name'].startswith('HD-'))
        self.assertNotEqual(created['state'], 'draft')
        escalations = Ui.load_screen('escalations', {})
        for key in ('needs', 'at_risk', 'breached', 'today', 'awaiting'):
            self.assertIn(key, escalations['kpis'])
        self.assertIn('rows', escalations)
        dummy_titles = {'AC Not Cooling', 'Water Leakage in Apartment', 'Elevator Noise', 'Cleaning Request'}
        self.assertFalse({row['title'] for row in escalations['rows']} & dummy_titles)
        resolution = Ui.load_screen('resolution', {})
        for key in ('needs', 'verify', 'close', 'closed_today', 'resolved_count', 'closed_count'):
            self.assertIn(key, resolution['kpis'])
        dummy_res = {'Water Leakage in Apartment', 'AC Not Cooling', 'Corridor Light Issue', 'Cleaning Request'}
        self.assertFalse({row['title'] for row in resolution['tickets']} & dummy_res)

    def test_work_queue_team_tab_filters_member_tickets(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Queue Plumbing',
            'default_team_id': self.team.id,
        })
        mine = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': 'My Queue Leak',
            'resident_id': self.resident.id,
            'category_id': category.id,
            'priority_id': self.high.id,
        })
        mine.action_submit()
        other_agent = new_test_user(
            self.env, login='fms_ui_other_agent', name='Other Agent',
            groups='fms_helpdesk.group_fms_helpdesk_agent')
        outsider_team = self.env['fms.helpdesk.team'].create({
            'name': 'Outside Team',
            'member_ids': [(6, 0, [other_agent.id])],
        })
        outsider_cat = self.env['fms.helpdesk.category'].create({
            'name': 'Outside Cat',
            'default_team_id': outsider_team.id,
        })
        other = self.env['fms.helpdesk.ticket'].with_user(other_agent).create({
            'title': 'Outside Ticket',
            'resident_id': self.resident.id,
            'category_id': outsider_cat.id,
            'priority_id': self.low.id,
        })
        other.action_submit()
        Ui = self.env['fms.helpdesk.ui'].with_user(self.agent)
        team_queue = Ui.load_screen('work_queue', {'tab': 'team'})
        ids = {row['id'] for row in team_queue['tickets']}
        self.assertIn(mine.id, ids)
        self.assertNotIn(other.id, ids)
        all_queue = Ui.load_screen('work_queue', {'tab': 'all'})
        all_ids = {row['id'] for row in all_queue['tickets']}
        self.assertIn(mine.id, all_ids)
        self.assertIn(other.id, all_ids)

    def test_resolution_verified_moves_to_close_action(self):
        self.env['ir.config_parameter'].sudo().set_param('fms_helpdesk.require_verification', 'True')
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Verify Plumbing',
            'default_team_id': self.team.id,
        })
        ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': 'Needs Verify Then Close',
            'resident_id': self.resident.id,
            'category_id': category.id,
            'priority_id': self.high.id,
        })
        ticket.action_submit()
        ticket.with_user(self.agent).action_start_progress()
        self.env['fms.helpdesk.ui'].with_user(self.agent).resolve_ticket(
            ticket.id, 'Fixed leak', 'Tested')
        ticket.invalidate_recordset()
        self.assertEqual(ticket.state, 'awaiting_verification')
        Ui = self.env['fms.helpdesk.ui'].with_user(self.admin_user)
        verify_tab = Ui.load_screen('resolution', {'tab': 'verify'})
        self.assertTrue(any(row['id'] == ticket.id and row['action'] == 'verify' for row in verify_tab['tickets']))
        Ui.verify_resolution(ticket.id, 'Looks good')
        ticket.invalidate_recordset()
        self.assertEqual(ticket.resolution_id.state, 'verified')
        close_tab = Ui.load_screen('resolution', {'tab': 'close'})
        self.assertTrue(any(row['id'] == ticket.id and row['action'] == 'close' for row in close_tab['tickets']))
        details = Ui.load_screen('ticket', {'ticket_id': ticket.id})
        self.assertEqual(details['ticket']['resolution_state'], 'verified')

    def test_header_global_search_filters_complaints(self):
        category = self.env['fms.helpdesk.category'].create({
            'name': 'Search Plumbing',
            'default_team_id': self.team.id,
        })
        ticket = self.env['fms.helpdesk.ticket'].with_user(self.agent).create({
            'title': 'UniqueSearchLeakXYZ',
            'resident_id': self.resident.id,
            'category_id': category.id,
            'priority_id': self.high.id,
        })
        ticket.action_submit()
        Ui = self.env['fms.helpdesk.ui'].with_user(self.admin_user)
        found = Ui.load_screen('complaints', {'global_search': 'UniqueSearchLeakXYZ'})
        self.assertTrue(any(row['id'] == ticket.id for row in found['tickets']))
        missing = Ui.load_screen('complaints', {'global_search': 'NoSuchTicketZZZ'})
        self.assertFalse(any(row['id'] == ticket.id for row in missing['tickets']))

    def test_settings_screen_exposes_reopen_and_feedback(self):
        Ui = self.env['fms.helpdesk.ui'].with_user(self.admin_user)
        data = Ui.load_screen('settings', {})
        for key in (
            'app_name', 'auto_routing', 'require_verification', 'allow_reopen',
            'reopen_days', 'feedback_enabled', 'low_rating_threshold',
        ):
            self.assertIn(key, data)
        Ui.save_settings({
            'allow_reopen': True,
            'reopen_days': 5,
            'feedback_enabled': False,
            'low_rating_threshold': 3,
        })
        refreshed = Ui.load_screen('settings', {})
        self.assertEqual(refreshed['reopen_days'], 5)
        self.assertFalse(refreshed['feedback_enabled'])
        self.assertEqual(refreshed['low_rating_threshold'], 3)
