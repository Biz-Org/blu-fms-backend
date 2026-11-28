# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wm_default_site = fields.Char(
        string='Default Facility / Site',
        config_parameter='waste_management.default_site',
        default='Site Alpha',
    )
    wm_default_uom_id = fields.Integer(
        string='Default Unit of Measure ID',
        config_parameter='waste_management.default_uom_id',
    )
    wm_default_storage_location_id = fields.Integer(
        string='Default Waste Storage Location ID',
        config_parameter='waste_management.default_storage_location_id',
    )
    wm_compliance_reminder_days = fields.Integer(
        string='Compliance Reminder Days',
        config_parameter='waste_management.compliance_reminder_days',
        default=30,
    )
    wm_collection_reminder_hours = fields.Integer(
        string='Collection Reminder (hours before)',
        config_parameter='waste_management.collection_reminder_hours',
        default=24,
    )
    wm_require_disposal_proof = fields.Boolean(
        string='Require Disposal Proof',
        config_parameter='waste_management.require_disposal_proof',
        default=True,
    )
    wm_segregation_required_default = fields.Boolean(
        string='Segregation Required by Default',
        config_parameter='waste_management.segregation_required_default',
        default=True,
    )


class WmConfig(models.TransientModel):
    _name = 'wm.config'
    _description = 'Waste Management Config API'
    _inherit = ['wm.api.mixin']

    @api.model
    def get_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return self._wm_ok({
            'default_site': ICP.get_param('waste_management.default_site', 'Site Alpha'),
            'default_uom_id': int(ICP.get_param('waste_management.default_uom_id') or 0) or False,
            'default_storage_location_id': int(ICP.get_param('waste_management.default_storage_location_id') or 0) or False,
            'compliance_reminder_days': int(ICP.get_param('waste_management.compliance_reminder_days', '30')),
            'collection_reminder_hours': int(ICP.get_param('waste_management.collection_reminder_hours', '24')),
            'require_disposal_proof': ICP.get_param('waste_management.require_disposal_proof', 'True') in ('True', '1', True),
            'segregation_required_default': ICP.get_param('waste_management.segregation_required_default', 'True') in ('True', '1', True),
            'sections': [
                {'title': 'General Preferences', 'text': 'Default site, date format, units and display options.'},
                {'title': 'Waste Categories & Types', 'text': 'Dry, Wet, Hazardous, E-Waste and related subtypes.'},
                {'title': 'Collection Zones', 'text': 'Zones, buildings, floors and preferred vendors.'},
                {'title': 'Recycling & Disposal Methods', 'text': 'Configured processing and disposal methods.'},
                {'title': 'Compliance Rules', 'text': 'Expiry thresholds, renewal lead times and reminders.'},
                {'title': 'Approval Workflows', 'text': 'Disposal approval, document verification hierarchy.'},
                {'title': 'Alerts & Notifications', 'text': 'Delay, miss, expiry and cost overrun channels.'},
                {'title': 'Cost Methods', 'text': 'Collection, recycling and disposal costing rules.'},
            ],
        })

    @api.model
    def save_settings(self, values=None):
        self._wm_require_group('waste_management.group_wm_manager')
        values = values or {}
        ICP = self.env['ir.config_parameter'].sudo()
        mapping = {
            'default_site': 'waste_management.default_site',
            'default_uom_id': 'waste_management.default_uom_id',
            'default_storage_location_id': 'waste_management.default_storage_location_id',
            'compliance_reminder_days': 'waste_management.compliance_reminder_days',
            'collection_reminder_hours': 'waste_management.collection_reminder_hours',
            'require_disposal_proof': 'waste_management.require_disposal_proof',
            'segregation_required_default': 'waste_management.segregation_required_default',
        }
        for key, param in mapping.items():
            if key in values and values[key] is not None:
                ICP.set_param(param, values[key])
        return self._wm_ok(message='Settings saved successfully')
