# -*- coding: utf-8 -*-

from odoo import fields, models

LIFECYCLE_EVENT_TYPES = [
    ("registration", "Registration"),
    ("classification", "Classification Change"),
    ("location", "Location Change"),
    ("assignment", "Assignment Change"),
    ("status", "Lifecycle Status"),
    ("warranty", "Warranty"),
    ("inspection", "Inspection"),
    ("maintenance", "Maintenance Reference"),
    ("transfer", "Transfer"),
    ("disposal", "Disposal"),
    ("financial", "Financial / Depreciation"),
]


class FmsAssetLifecycleEvent(models.Model):
    _name = "fms.asset.lifecycle.event"
    _description = "FMS Asset Lifecycle Event"
    _order = "event_date desc, id desc"

    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    event_type = fields.Selection(LIFECYCLE_EVENT_TYPES, required=True, index=True)
    event_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    summary = fields.Char(required=True)
    details = fields.Text()