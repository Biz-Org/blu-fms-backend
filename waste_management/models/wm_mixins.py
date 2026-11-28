# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError


class WmApiMixin(models.AbstractModel):
    _name = 'wm.api.mixin'
    _description = 'Waste Management API Helpers'

    @api.model
    def _wm_ok(self, data=None, message='Operation completed successfully'):
        return {'success': True, 'message': message, 'data': data or {}}

    @api.model
    def _wm_fail(self, message, data=None):
        return {'success': False, 'message': message or 'Operation failed', 'data': data or {}}

    @api.model
    def _wm_selection_label(self, record, field_name):
        field = record._fields.get(field_name)
        if not field or not getattr(field, 'selection', None):
            return ''
        value = record[field_name]
        return dict(field.selection).get(value, value or '')

    @api.model
    def _wm_date(self, value):
        return fields.Date.to_string(value) if value else ''

    @api.model
    def _wm_datetime(self, value):
        return fields.Datetime.to_string(value) if value else ''

    @api.model
    def _wm_require_group(self, xmlid):
        if not self.env.user.has_group(xmlid) and not self.env.user.has_group('waste_management.group_wm_manager'):
            raise AccessError('You do not have permission to perform this action.')

    @api.model
    def _wm_assert_transition(self, record, allowed, action_name='this action'):
        if record.state not in allowed:
            raise UserError('Cannot perform %s from state "%s".' % (action_name, record.state))

    @api.model
    def _wm_log(self, action, record, description='', previous_value='', new_value=''):
        Audit = self.env.get('wm.audit')
        if Audit is None:
            return
        Audit.sudo().create({
            'action': action,
            'res_model': record._name,
            'res_id': record.id,
            'res_name': record.display_name,
            'user_id': self.env.user.id,
            'previous_value': previous_value or '',
            'new_value': new_value or '',
            'notes': description or action,
        })
