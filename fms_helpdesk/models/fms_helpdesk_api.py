# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import html2plaintext

from odoo.addons.fms_helpdesk.models.fms_helpdesk_access import (
    GROUP_AGENT,
    GROUP_MANAGER,
    GROUP_RESIDENT,
    GROUP_TEAM_LEAD,
    GROUP_ADMIN,
)


class FmsHelpdeskApiError(Exception):
    """Controlled API failure with a stable error code and HTTP status."""

    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class FmsHelpdeskApi(models.AbstractModel):
    """JSON API facade for external Mobile Helpdesk clients.

    Controllers stay thin. Routing, SLA, escalation, resolution and closure
    stay on ``fms.helpdesk.ticket`` and related models.
    """

    _name = 'fms.helpdesk.api'
    _description = 'Helpdesk Mobile API'

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    def _api_user(self):
        return self.env.user

    def _ensure_helpdesk_user(self):
        user = self._api_user()
        if user._is_public() or user.id == self.env.ref('base.public_user').id:
            raise FmsHelpdeskApiError('UNAUTHORIZED', _('Authentication required.'), 401)
        allowed = (
            user.has_group(GROUP_RESIDENT)
            or user.has_group(GROUP_AGENT)
            or user.has_group(GROUP_TEAM_LEAD)
            or user.has_group(GROUP_MANAGER)
            or user.has_group(GROUP_ADMIN)
            or user.has_group('fms_helpdesk.group_fms_helpdesk_viewer')
        )
        if not allowed:
            raise FmsHelpdeskApiError(
                'UNAUTHORIZED', _('You are not allowed to use the Helpdesk API.'), 401)

    def _is_resident_only(self):
        user = self._api_user()
        return user.has_group(GROUP_RESIDENT) and not user.has_group(GROUP_AGENT)

    def _ticket(self):
        return self.env['fms.helpdesk.ticket']

    def _get_ticket(self, ticket_id):
        try:
            ticket_id = int(ticket_id)
        except (TypeError, ValueError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', _('Invalid ticket id.'), 400) from err
        ticket = self._ticket().search([('id', '=', ticket_id)], limit=1)
        if ticket:
            return ticket
        if self._ticket().sudo().browse(ticket_id).exists():
            raise FmsHelpdeskApiError('UNAUTHORIZED', _('You cannot access this ticket.'), 401)
        raise FmsHelpdeskApiError('NOT_FOUND', _('Ticket not found.'), 404)

    def _require_int(self, payload, key, required=True):
        value = payload.get(key)
        if value in (None, False, ''):
            if required:
                raise FmsHelpdeskApiError('VALIDATION_ERROR', _('%s is required.', key), 400)
            return False
        try:
            return int(value)
        except (TypeError, ValueError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', _('%s must be an integer.', key), 400) from err

    def _require_str(self, payload, key, required=True):
        value = payload.get(key)
        if value in (None, False):
            if required:
                raise FmsHelpdeskApiError('VALIDATION_ERROR', _('%s is required.', key), 400)
            return False
        text = str(value).strip()
        if required and not text:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', _('%s is required.', key), 400)
        return text or False

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _ticket_summary(self, ticket):
        return {
            'id': ticket.id,
            'name': ticket.name or False,
            'title': ticket.title or '',
            'state': ticket.state,
            'state_label': dict(ticket._fields['state'].selection).get(ticket.state, ticket.state),
            'category': ticket.category_id.name or False,
            'category_id': ticket.category_id.id or False,
            'subcategory': ticket.subcategory_id.name or False,
            'subcategory_id': ticket.subcategory_id.id or False,
            'priority': ticket.priority_id.name or False,
            'priority_id': ticket.priority_id.id or False,
            'priority_code': ticket.priority_id.code or False,
            'team': ticket.team_id.name or False,
            'assignee': ticket.user_id.name or False,
            'sla_status': ticket.sla_status or False,
            'sla_label': ticket.sla_remaining_label or False,
            'sla_breached': bool(ticket.sla_breached),
            'created': fields.Datetime.to_string(ticket.create_date) if ticket.create_date else False,
            'updated': fields.Datetime.to_string(ticket.write_date) if ticket.write_date else False,
        }

    def _ticket_detail(self, ticket):
        data = self._ticket_summary(ticket)
        data.update({
            'description': html2plaintext(ticket.description or '') or '',
            'resident': ticket.resident_id.name or False,
            'resident_id': ticket.resident_id.id or False,
            'building': ticket.building_name or False,
            'unit': ticket.unit_name or False,
            'property': ticket.property_name or False,
            'location_type': ticket.location_type or False,
            'location_detail': ticket.location_detail or False,
            'channel': ticket.channel,
            'team_id': ticket.team_id.id or False,
            'user_id': ticket.user_id.id or False,
            'sla_policy': ticket.sla_policy_id.name or False,
            'response_deadline': fields.Datetime.to_string(ticket.response_deadline) if ticket.response_deadline else False,
            'resolution_deadline': fields.Datetime.to_string(ticket.resolution_deadline) if ticket.resolution_deadline else False,
            'is_escalated': bool(ticket.is_escalated),
            'escalation_level': ticket.escalation_level_id.name or False,
            'resolution': html2plaintext(ticket.resolution_id.description or '') if ticket.resolution_id else '',
            'rating': ticket.rating or 0,
            'history': [{
                'id': line.id,
                'action': line.action,
                'time': fields.Datetime.to_string(line.create_date) if line.create_date else False,
                'user': line.user_id.name or '',
                'old': line.old_value or '',
                'new': line.new_value or '',
                'remarks': line.remarks or '',
            } for line in ticket.history_ids[:40]],
            'attachments': [{
                'id': att.id,
                'name': att.name,
                'mimetype': att.mimetype or False,
                'file_size': att.file_size,
            } for att in ticket.attachment_ids],
            'feedback': [{
                'id': fb.id,
                'state': fb.state,
                'rating': fb.rating_value,
                'comment': fb.comment or '',
            } for fb in ticket.feedback_ids],
        })
        return data

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    @api.model
    def api_masters(self):
        self._ensure_helpdesk_user()
        Category = self.env['fms.helpdesk.category']
        categories = []
        for category in Category.search([]):
            categories.append({
                'id': category.id,
                'name': category.name,
                'subcategories': [{'id': s.id, 'name': s.name} for s in category.subcategory_ids],
            })
        return {
            'user': {
                'id': self.env.user.id,
                'name': self.env.user.name,
                'login': self.env.user.login,
                'is_resident': self._is_resident_only(),
            },
            'categories': categories,
            'priorities': [
                {'id': p.id, 'name': p.name, 'code': p.code}
                for p in self.env['fms.helpdesk.priority'].search([])
            ],
            'teams': [
                {'id': t.id, 'name': t.name}
                for t in self.env['fms.helpdesk.team'].search([])
            ],
            'escalation_levels': [
                {'id': level.id, 'name': level.name, 'level': level.level}
                for level in self.env['fms.helpdesk.escalation.level'].search([])
            ],
        }

    @api.model
    def api_list_tickets(self, params=None):
        self._ensure_helpdesk_user()
        params = params or {}
        domain = [('state', '!=', 'draft')] if not params.get('include_draft') else []
        search = (params.get('search') or '').strip()
        if search:
            domain = expression.AND([domain, [
                '|', '|',
                ('name', 'ilike', search),
                ('title', 'ilike', search),
                ('description', 'ilike', search),
            ]])
        if params.get('state'):
            states = params['state'] if isinstance(params['state'], list) else [params['state']]
            domain.append(('state', 'in', states))
        if params.get('category_id'):
            domain.append(('category_id', '=', self._require_int(params, 'category_id')))
        if params.get('priority_id'):
            domain.append(('priority_id', '=', self._require_int(params, 'priority_id')))
        if params.get('mine'):
            if self._is_resident_only():
                domain = expression.AND([domain, [
                    '|',
                    ('resident_id', '=', self.env.user.partner_id.id),
                    ('reported_by_id', '=', self.env.user.id),
                ]])
            else:
                domain.append(('user_id', '=', self.env.user.id))
        limit = min(max(self._require_int({'limit': params.get('limit') or 50}, 'limit'), 1), 200)
        offset = max(self._require_int({'offset': params.get('offset') or 0}, 'offset', required=False) or 0, 0)
        Ticket = self._ticket()
        total = Ticket.search_count(domain)
        tickets = Ticket.search(domain, limit=limit, offset=offset, order='id desc')
        return {
            'total': total,
            'limit': limit,
            'offset': offset,
            'tickets': [self._ticket_summary(ticket) for ticket in tickets],
        }

    @api.model
    def api_get_ticket(self, ticket_id):
        self._ensure_helpdesk_user()
        return self._ticket_detail(self._get_ticket(ticket_id))

    @api.model
    def api_create_ticket(self, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        title = self._require_str(payload, 'title')
        category_id = self._require_int(payload, 'category_id')
        priority_id = self._require_int(payload, 'priority_id', required=False)
        subcategory_id = self._require_int(payload, 'subcategory_id', required=False)
        submit = bool(payload.get('submit', True))
        description = self._require_str(payload, 'description', required=False) or ''
        html = description if description.startswith('<') else '<p>%s</p>' % description.replace('\n', '<br/>')

        vals = {
            'title': title,
            'description': html,
            'category_id': category_id,
            'subcategory_id': subcategory_id or False,
            'channel': 'mobile',
            'state': 'draft' if not submit else 'new',
        }
        if priority_id:
            vals['priority_id'] = priority_id
        if self._is_resident_only():
            vals['resident_id'] = self.env.user.partner_id.id
        else:
            resident_id = self._require_int(payload, 'resident_id', required=False)
            if resident_id:
                vals['resident_id'] = resident_id
            contact_name = self._require_str(payload, 'contact_name', required=False)
            if contact_name:
                vals['contact_name'] = contact_name
            if not vals.get('resident_id') and not vals.get('contact_name'):
                raise FmsHelpdeskApiError(
                    'VALIDATION_ERROR', _('resident_id or contact_name is required.'), 400)
        for name in ('property_name', 'building_name', 'unit_name', 'location_detail', 'visit_notes'):
            value = self._require_str(payload, name, required=False)
            if value:
                vals[name] = value
        if payload.get('location_type'):
            vals['location_type'] = payload['location_type']

        try:
            ticket = self._ticket().create(vals)
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_add_update(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        note = self._require_str(payload, 'note')
        try:
            ticket.message_post(body=note, message_type='comment', subtype_xmlid='mail.mt_comment')
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_assign(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        try:
            ticket.action_assign(
                team_id=self._require_int(payload, 'team_id', required=False) or None,
                user_id=self._require_int(payload, 'user_id', required=False) or None,
                reason=self._require_str(payload, 'reason', required=False) or False,
            )
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_escalate(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        try:
            ticket.action_escalate(
                level_id=self._require_int(payload, 'level_id', required=False) or None,
                reason=self._require_str(payload, 'reason', required=False) or 'manual',
                comment=self._require_str(payload, 'comment', required=False) or False,
            )
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_resolve(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        try:
            ticket.action_add_resolution(
                self._require_str(payload, 'description'),
                self._require_str(payload, 'work_performed', required=False) or False,
            )
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_verify(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        if not ticket.resolution_id:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', _('This complaint has no resolution to verify.'), 400)
        try:
            ticket.resolution_id.action_verify(self._require_str(payload, 'remarks', required=False) or False)
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_close(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        try:
            ticket.action_close(
                reason=self._require_str(payload, 'reason', required=False) or 'resolved',
                comment=self._require_str(payload, 'comment', required=False) or False,
            )
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_reopen(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        try:
            ticket.action_reopen(self._require_str(payload, 'reason'))
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return self._ticket_detail(ticket)

    @api.model
    def api_feedback(self, ticket_id, payload=None):
        self._ensure_helpdesk_user()
        payload = payload or {}
        ticket = self._get_ticket(ticket_id)
        rating = self._require_str(payload, 'rating')
        if rating not in {'1', '2', '3', '4', '5'}:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', _('rating must be 1 to 5.'), 400)
        comment = self._require_str(payload, 'comment', required=False) or False
        feedback = ticket.feedback_ids.filtered(lambda f: f.state == 'pending')[:1]
        try:
            if feedback:
                feedback.write({'rating': rating, 'comment': comment})
            else:
                feedback = self.env['fms.helpdesk.feedback'].create({
                    'ticket_id': ticket.id,
                    'rating': rating,
                    'comment': comment,
                    'state': 'submitted',
                })
        except (UserError, ValidationError) as err:
            raise FmsHelpdeskApiError('VALIDATION_ERROR', str(err), 400) from err
        except AccessError as err:
            raise FmsHelpdeskApiError('UNAUTHORIZED', str(err), 401) from err
        return {
            'ticket': self._ticket_detail(ticket),
            'feedback': {
                'id': feedback.id,
                'state': feedback.state,
                'rating': feedback.rating_value,
                'comment': feedback.comment or '',
            },
        }
