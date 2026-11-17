# -*- coding: utf-8 -*-

import json
import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.fms_helpdesk.models.fms_helpdesk_api import FmsHelpdeskApiError

_logger = logging.getLogger(__name__)


class FmsHelpdeskApiController(http.Controller):
    """Authenticated JSON API for Mobile Helpdesk and other external clients.

    The in-Odoo OWL screens keep using session ORM RPC (``fms.helpdesk.ui``).
    These HTTP routes exist for clients that cannot call the ORM directly.
    """

    def _json_body(self):
        raw = request.httprequest.data or b''
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', 'Invalid JSON body.', 400) from err
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise FmsHelpdeskApiError('VALIDATION_ERROR', 'JSON body must be an object.', 400)
        return data

    def _query_params(self):
        args = request.httprequest.args
        params = {}
        for key in args:
            values = args.getlist(key)
            params[key] = values if len(values) > 1 else values[0]
        if 'mine' in params:
            params['mine'] = str(params['mine']).lower() in ('1', 'true', 'yes')
        if 'include_draft' in params:
            params['include_draft'] = str(params['include_draft']).lower() in ('1', 'true', 'yes')
        for key in ('limit', 'offset', 'category_id', 'priority_id'):
            if key in params and not isinstance(params[key], list):
                try:
                    params[key] = int(params[key])
                except (TypeError, ValueError):
                    pass
        return params

    def _request_id(self):
        return (
            request.httprequest.headers.get('X-Request-Id')
            or request.httprequest.headers.get('X-Request-ID')
            or ''
        )

    def _api_env(self):
        uid = request.session.uid
        if not uid:
            raise FmsHelpdeskApiError('UNAUTHORIZED', 'Authentication required.', 401)
        return request.env(user=uid)

    def _ok(self, data, status=200):
        body = {'success': True, 'data': data, 'error': None}
        rid = self._request_id()
        if rid:
            body['request_id'] = rid
        return request.make_json_response(body, status=status)

    def _fail(self, code, message, status=400):
        body = {
            'success': False,
            'data': None,
            'error': {'code': code, 'message': message},
        }
        rid = self._request_id()
        if rid:
            body['request_id'] = rid
        return request.make_json_response(body, status=status)

    def _dispatch(self, handler):
        try:
            env = self._api_env()
            return self._ok(handler(env))
        except FmsHelpdeskApiError as err:
            return self._fail(err.code, err.message, status=err.http_status)
        except UserError as err:
            return self._fail('VALIDATION_ERROR', str(err), status=400)
        except AccessError as err:
            return self._fail('UNAUTHORIZED', str(err), status=401)
        except Exception:
            _logger.exception('FMS Helpdesk API unexpected error')
            return self._fail('SERVER_ERROR', 'Unexpected server error.', status=500)

    # ---- Routes ----

    @http.route(
        '/fms/helpdesk/api/v1/masters',
        type='http', auth='public', methods=['GET'], csrf=False,
    )
    def masters(self, **kwargs):
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_masters())

    @http.route(
        '/fms/helpdesk/api/v1/tickets',
        type='http', auth='public', methods=['GET'], csrf=False,
    )
    def list_tickets(self, **kwargs):
        params = self._query_params()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_list_tickets(params))

    @http.route(
        '/fms/helpdesk/api/v1/tickets',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def create_ticket(self, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_create_ticket(body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>',
        type='http', auth='public', methods=['GET'], csrf=False,
    )
    def get_ticket(self, ticket_id, **kwargs):
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_get_ticket(ticket_id))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/updates',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def add_update(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_add_update(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/assign',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def assign_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_assign(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/escalate',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def escalate_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_escalate(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/resolve',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def resolve_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_resolve(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/verify',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def verify_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_verify(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/close',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def close_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_close(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/reopen',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def reopen_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_reopen(ticket_id, body))

    @http.route(
        '/fms/helpdesk/api/v1/tickets/<int:ticket_id>/feedback',
        type='http', auth='public', methods=['POST'], csrf=False,
    )
    def feedback_ticket(self, ticket_id, **kwargs):
        body = self._json_body()
        return self._dispatch(lambda env: env['fms.helpdesk.api'].api_feedback(ticket_id, body))
