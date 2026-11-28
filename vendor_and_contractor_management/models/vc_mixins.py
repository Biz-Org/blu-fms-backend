# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError


GSTIN_RE = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')
PAN_RE = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')


class VcApiMixin(models.AbstractModel):
    _name = 'vc.api.mixin'
    _description = 'Vendor Contractor API Helpers'

    @api.model
    def _vc_ok(self, data=None, message='Operation completed successfully'):
        return {'success': True, 'message': message, 'data': data or {}}

    @api.model
    def _vc_fail(self, message, data=None):
        return {'success': False, 'message': message or 'Operation failed', 'data': data or {}}

    @api.model
    def _vc_selection_label(self, record, field_name):
        field = record._fields.get(field_name)
        if not field or not getattr(field, 'selection', None):
            return ''
        value = record[field_name]
        return dict(field.selection).get(value, value or '')

    @api.model
    def _vc_date(self, value):
        if not value:
            return ''
        return fields.Date.to_string(value)

    @api.model
    def _vc_datetime(self, value):
        if not value:
            return ''
        return fields.Datetime.to_string(value)

    @api.model
    def _vc_log(self, activity_type, record, description='', previous_state=False, new_state=False, site_id=False):
        Activity = self.env.get('vc.activity')
        if Activity is None:
            return
        Activity.sudo().create({
            'activity_type': activity_type,
            'res_model': record._name,
            'res_id': record.id,
            'res_name': record.display_name,
            'user_id': self.env.user.id,
            'site_id': site_id.id if site_id else (getattr(record, 'site_id', False) and record.site_id.id or False),
            'description': description or activity_type,
            'previous_state': previous_state or '',
            'new_state': new_state or '',
        })

    @api.model
    def _vc_notify(self, title, message, category='general', res_model=False, res_id=False, severity='info'):
        Notification = self.env.get('vc.notification')
        if Notification is None:
            return
        # Avoid duplicates for same open notification same day
        domain = [
            ('title', '=', title),
            ('res_model', '=', res_model or False),
            ('res_id', '=', res_id or False),
            ('is_read', '=', False),
            ('create_date', '>=', fields.Datetime.now().replace(hour=0, minute=0, second=0)),
        ]
        if Notification.sudo().search_count(domain):
            return
        Notification.sudo().create({
            'title': title,
            'message': message,
            'category': category,
            'severity': severity,
            'res_model': res_model or False,
            'res_id': res_id or False,
            'user_id': self.env.user.id,
        })

    @api.model
    def _vc_require_group(self, xmlid):
        if not self.env.user.has_group(xmlid) and not self.env.user.has_group('vendor_and_contractor_management.group_vc_manager'):
            raise AccessError('You do not have permission to perform this action.')

    @api.model
    def _vc_validate_gstin(self, gstin):
        if not gstin:
            return
        value = gstin.strip().upper()
        if not GSTIN_RE.match(value):
            raise ValidationError('Invalid GSTIN format.')

    @api.model
    def _vc_validate_pan(self, pan):
        if not pan:
            return
        value = pan.strip().upper()
        if not PAN_RE.match(value):
            raise ValidationError('Invalid PAN format.')

    @api.model
    def _vc_assert_transition(self, record, allowed, action_name='this action'):
        if record.state not in allowed:
            raise UserError('Cannot perform %s from state "%s".' % (action_name, record.state))
