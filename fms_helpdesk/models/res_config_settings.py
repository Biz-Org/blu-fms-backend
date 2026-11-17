# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import AccessError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fms_helpdesk_default_priority_id = fields.Many2one(
        'fms.helpdesk.priority', string='Default Priority', config_parameter='fms_helpdesk.default_priority_id')
    fms_helpdesk_auto_routing = fields.Boolean(
        string='Automatic Routing', config_parameter='fms_helpdesk.auto_routing')
    fms_helpdesk_reassign_reason_required = fields.Boolean(
        string='Reason Required on Reassignment', config_parameter='fms_helpdesk.reassign_reason_required')
    fms_helpdesk_require_verification = fields.Boolean(
        string='Verify Resolution Before Closure', config_parameter='fms_helpdesk.require_verification')
    fms_helpdesk_allow_reopen = fields.Boolean(
        string='Allow Reopening', config_parameter='fms_helpdesk.allow_reopen')
    fms_helpdesk_reopen_days = fields.Integer(
        string='Reopen Window (days)', config_parameter='fms_helpdesk.reopen_days',
        help="0 means closed tickets can be reopened at any time.")
    fms_helpdesk_allow_resident_attachments = fields.Boolean(
        string='Allow Resident Attachments', config_parameter='fms_helpdesk.allow_resident_attachments')
    fms_helpdesk_allow_multiple_attachments = fields.Boolean(
        string='Allow Multiple Attachments', config_parameter='fms_helpdesk.allow_multiple_attachments')
    fms_helpdesk_max_attachment_size_mb = fields.Integer(
        string='Max Attachment Size (MB)', config_parameter='fms_helpdesk.max_attachment_size_mb')
    fms_helpdesk_allowed_attachment_types = fields.Char(
        string='Allowed File Types', config_parameter='fms_helpdesk.allowed_attachment_types')
    fms_helpdesk_feedback_enabled = fields.Boolean(
        string='Request Feedback on Closure', config_parameter='fms_helpdesk.feedback_enabled')
    fms_helpdesk_low_rating_threshold = fields.Integer(
        string='Low Rating Threshold', config_parameter='fms_helpdesk.low_rating_threshold')

    def set_values(self):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('fms_helpdesk.group_fms_helpdesk_admin'):
            stored = self.get_values()
            for name, field in self._fields.items():
                if not name.startswith('fms_helpdesk_') or not getattr(field, 'config_parameter', None):
                    continue
                new = self[name]
                old = stored.get(name)
                if field.type == 'many2one':
                    new = new.id if new else False
                    old = old or False
                elif field.type == 'boolean':
                    new, old = bool(new), bool(old)
                if new != old:
                    raise AccessError(_("Only a Helpdesk Administrator can change Helpdesk Settings."))
        return super().set_values()
