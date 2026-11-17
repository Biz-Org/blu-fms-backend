# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .constants import CONDITION_STATES, HEALTH_STATUSES


class FmsAssetInspection(models.Model):
    _name = "fms.asset.inspection"
    _description = "FMS Asset Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "inspection_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    inspection_date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        index=True,
        tracking=True,
    )
    inspector_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    condition = fields.Selection(CONDITION_STATES, tracking=True)
    health_status = fields.Selection(HEALTH_STATUSES, tracking=True)
    health_score = fields.Float(tracking=True)
    observations = fields.Text()
    findings = fields.Text()
    recommended_actions = fields.Text()
    temperature = fields.Float()
    vibration = fields.Float()
    pressure = fields.Float()
    state = fields.Selection(
        [("draft", "Draft"), ("completed", "Completed")],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    def action_complete(self):
        for record in self:
            if record.equipment_id.fms_operations_locked:
                raise ValidationError(_("Cannot inspect a disposed asset."))
            record.write({"state": "completed"})
            equipment_vals = {}
            if record.condition:
                equipment_vals["fms_condition"] = record.condition
            if record.health_status:
                equipment_vals["fms_health_status"] = record.health_status
            if equipment_vals:
                record.equipment_id.write(equipment_vals)
            record.equipment_id._fms_log_lifecycle_event(
                "inspection",
                _("Inspection completed: %(name)s", name=record.name),
                record.findings,
            )
        return True

    @api.model
    def fms_create_inspection(self, equipment_id, payload):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create inspections."))
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        if equipment.fms_operations_locked:
            raise ValidationError(_("Cannot inspect a disposed asset."))
        inspection = self.create(
            {
                "name": payload.get("name") or _("Inspection"),
                "equipment_id": equipment.id,
                "condition": payload.get("condition") or False,
                "health_status": payload.get("health_status") or False,
                "health_score": float(payload.get("health_score") or 0.0) or False,
                "observations": payload.get("observations") or False,
                "findings": payload.get("findings") or False,
                "recommended_actions": payload.get("recommended_actions") or False,
                "temperature": float(payload.get("temperature") or 0.0) or False,
                "vibration": float(payload.get("vibration") or 0.0) or False,
                "pressure": float(payload.get("pressure") or 0.0) or False,
            }
        )
        if payload.get("complete"):
            inspection.action_complete()
        return {"id": inspection.id}