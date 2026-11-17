# -*- coding: utf-8 -*-

import json

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'fms_helpdesk')
class TestFmsHelpdeskApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = new_test_user(
            cls.env, login='fms_api_agent', name='API Agent',
            groups='fms_helpdesk.group_fms_helpdesk_agent', password='agent-pass')
        cls.lead = new_test_user(
            cls.env, login='fms_api_lead', name='API Lead',
            groups='fms_helpdesk.group_fms_helpdesk_team_lead', password='lead-pass')
        cls.outsider = new_test_user(
            cls.env, login='fms_api_outsider', name='API Outsider',
            groups='base.group_user', password='out-pass')
        cls.priority = cls.env['fms.helpdesk.priority'].create({
            'name': 'API High', 'code': 'api_high', 'sequence': 2, 'is_urgent': True,
        })
        cls.env['fms.helpdesk.sla.policy'].create({
            'name': 'API High SLA',
            'priority_id': cls.priority.id,
            'response_target': 30,
            'response_unit': 'minutes',
            'resolution_target': 4,
            'resolution_unit': 'hours',
            'coverage': '24x7',
        })
        cls.team = cls.env['fms.helpdesk.team'].create({
            'name': 'API Team',
            'leader_id': cls.lead.id,
            'member_ids': [(6, 0, [cls.agent.id])],
        })
        cls.category = cls.env['fms.helpdesk.category'].create({
            'name': 'API Plumbing',
            'default_team_id': cls.team.id,
            'default_user_id': cls.agent.id,
        })
        cls.resident = cls.env['res.partner'].create({
            'name': 'API Resident',
            'fms_is_resident': True,
            'fms_building_name': 'Tower API',
            'fms_unit_name': 'A-1',
        })

    def _headers(self, request_id=None):
        headers = {'Content-Type': 'application/json'}
        if request_id:
            headers['X-Request-Id'] = request_id
        return headers

    def _get(self, path, auth_user=None, password=None):
        if auth_user:
            self.authenticate(auth_user.login, password or auth_user.login)
        else:
            self.authenticate(None, None)
        return self.url_open(path, timeout=30)

    def _post(self, path, payload, auth_user=None, password=None, request_id=None):
        if auth_user:
            self.authenticate(auth_user.login, password or auth_user.login)
        else:
            self.authenticate(None, None)
        return self.url_open(
            path,
            data=json.dumps(payload),
            headers=self._headers(request_id),
            timeout=30,
        )

    def _json(self, response):
        self.assertTrue(response.headers.get('Content-Type', '').startswith('application/json'), response.text)
        return response.json()

    def test_unauthorized_without_session(self):
        response = self._get('/fms/helpdesk/api/v1/masters')
        body = self._json(response)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(body['success'])
        self.assertEqual(body['error']['code'], 'UNAUTHORIZED')

    def test_unauthorized_without_helpdesk_group(self):
        response = self._get('/fms/helpdesk/api/v1/masters', auth_user=self.outsider, password='out-pass')
        body = self._json(response)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body['error']['code'], 'UNAUTHORIZED')

    def test_masters_and_create_list_get_success(self):
        response = self._get('/fms/helpdesk/api/v1/masters', auth_user=self.agent, password='agent-pass')
        body = self._json(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body['success'])
        self.assertTrue(any(c['id'] == self.category.id for c in body['data']['categories']))

        create = self._post('/fms/helpdesk/api/v1/tickets', {
            'title': 'API Leak',
            'description': 'Pipe drip',
            'category_id': self.category.id,
            'priority_id': self.priority.id,
            'resident_id': self.resident.id,
            'submit': True,
        }, auth_user=self.agent, password='agent-pass', request_id='req-1')
        created = self._json(create)
        self.assertEqual(create.status_code, 200, created)
        self.assertTrue(created['success'])
        self.assertEqual(created['request_id'], 'req-1')
        ticket = created['data']
        self.assertTrue(ticket['name'].startswith('HD-'))
        self.assertEqual(ticket['state'], 'assigned')
        self.assertEqual(ticket['assignee'], 'API Agent')

        listing = self._get(
            '/fms/helpdesk/api/v1/tickets?search=API%20Leak',
            auth_user=self.agent, password='agent-pass')
        listed = self._json(listing)
        self.assertTrue(any(row['id'] == ticket['id'] for row in listed['data']['tickets']))

        detail = self._get(
            '/fms/helpdesk/api/v1/tickets/%s' % ticket['id'],
            auth_user=self.agent, password='agent-pass')
        detailed = self._json(detail)
        self.assertEqual(detailed['data']['id'], ticket['id'])
        self.assertIn('history', detailed['data'])

    def test_validation_error_on_create(self):
        response = self._post('/fms/helpdesk/api/v1/tickets', {
            'description': 'Missing title',
            'category_id': self.category.id,
            'resident_id': self.resident.id,
        }, auth_user=self.agent, password='agent-pass')
        body = self._json(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body['error']['code'], 'VALIDATION_ERROR')
        self.assertIn('title', body['error']['message'].lower())

    def test_missing_ticket_returns_not_found(self):
        response = self._get('/fms/helpdesk/api/v1/tickets/99999999', auth_user=self.agent, password='agent-pass')
        body = self._json(response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(body['error']['code'], 'NOT_FOUND')

    def test_resolve_close_via_api_reuses_orm(self):
        create = self._post('/fms/helpdesk/api/v1/tickets', {
            'title': 'API Resolve Flow',
            'category_id': self.category.id,
            'priority_id': self.priority.id,
            'resident_id': self.resident.id,
        }, auth_user=self.agent, password='agent-pass')
        ticket_id = self._json(create)['data']['id']
        ticket = self.env['fms.helpdesk.ticket'].browse(ticket_id)
        ticket.with_user(self.agent).write({'state': 'in_progress'})

        resolve = self._post(
            '/fms/helpdesk/api/v1/tickets/%s/resolve' % ticket_id,
            {'description': 'Fixed leak', 'work_performed': 'Replaced washer'},
            auth_user=self.agent, password='agent-pass')
        resolved = self._json(resolve)
        self.assertTrue(resolved['success'], resolved)
        self.assertIn(resolved['data']['state'], ('resolved', 'awaiting_verification'))

        close = self._post(
            '/fms/helpdesk/api/v1/tickets/%s/close' % ticket_id,
            {'reason': 'resolved', 'comment': 'Closed from API'},
            auth_user=self.lead, password='lead-pass')
        closed = self._json(close)
        self.assertTrue(closed['success'], closed)
        self.assertEqual(closed['data']['state'], 'closed')
        self.assertTrue(ticket.feedback_ids)
