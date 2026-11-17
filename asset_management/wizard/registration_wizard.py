# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from ..models.constants import CONDITION_STATES, DEPRECIATION_METHODS, LIFECYCLE_STATES


class FmsAssetRegistrationWizard(models.TransientModel):
    _name = "fms.asset.registration.wizard"
    _description = "FMS Asset Registration Wizard"

    step = fields.Selection(
        [
            ("basic", "Basic Information"),
            ("location", "Location"),
            ("purchase", "Purchase / Acquisition"),
            ("financial", "Financial Information"),
            ("documents", "Documents"),
            ("review", "Review"),
        ],
        default="basic",
        required=True,
    )
    name = fields.Char(required=True)
    fms_classification_id = fields.Many2one(
        "fms.asset.classification",
        domain="[('level', '=', 'subtype')]",
    )
    model = fields.Char()
    serial_no = fields.Char()
    fms_manufacturer = fields.Char()
    note = fields.Html()
    fms_location_id = fields.Many2one(
        "fms.asset.location",
        domain="[('location_type', '=', 'room')]",
    )
    fms_acquisition_date = fields.Date()
    partner_id = fields.Many2one("res.partner", string="Vendor")
    fms_purchase_order_ref = fields.Char(string="Purchase Order Reference")
    fms_invoice_ref = fields.Char(string="Invoice Reference")
    cost = fields.Float(string="Acquisition Cost")
    fms_residual_value = fields.Monetary(currency_field="fms_currency_id")
    fms_currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    fms_useful_life_months = fields.Integer(string="Useful Life (months)")
    fms_depreciation_method = fields.Selection(DEPRECIATION_METHODS)
    fms_condition = fields.Selection(CONDITION_STATES, default="good")
    fms_lifecycle_state = fields.Selection(LIFECYCLE_STATES, default="draft")
    fms_confirm_active = fields.Boolean(
        string="Activate on create",
        default=True,
        help="Set lifecycle status to Active when the asset is created.",
    )
    attachment_description = fields.Char(string="Document Note")

    def _validate_step(self, step):
        if step == "basic" and not self.name:
            raise ValidationError(_("Asset name is required."))

    @api.model
    def fms_register_asset(self, payload):
        """Create a maintenance equipment record from the OWL registration flow."""
        if not self.env["maintenance.equipment"].has_access("create"):
            raise ValidationError(_("You are not allowed to register assets."))
        if not payload.get("name"):
            raise ValidationError(_("Asset name is required."))
        classification_id = payload.get("fms_classification_id")
        if classification_id:
            classification = self.env["fms.asset.classification"].browse(int(classification_id))
            if classification.level != "subtype":
                raise ValidationError(_("Select a sub-type classification."))

        lifecycle = payload.get("fms_lifecycle_state") or "draft"
        if payload.get("fms_confirm_active"):
            lifecycle = "active"

        vals = {
            "name": payload["name"].strip(),
            "model": (payload.get("model") or "").strip() or False,
            "serial_no": (payload.get("serial_no") or "").strip() or False,
            "fms_manufacturer": (payload.get("fms_manufacturer") or "").strip() or False,
            "note": payload.get("note") or False,
            "fms_classification_id": int(classification_id) if classification_id else False,
            "fms_location_id": int(payload["fms_location_id"]) if payload.get("fms_location_id") else False,
            "fms_acquisition_date": payload.get("fms_acquisition_date") or False,
            "partner_id": int(payload["partner_id"]) if payload.get("partner_id") else False,
            "fms_purchase_order_ref": (payload.get("fms_purchase_order_ref") or "").strip() or False,
            "fms_invoice_ref": (payload.get("fms_invoice_ref") or "").strip() or False,
            "effective_date": payload.get("fms_acquisition_date") or fields.Date.context_today(self),
            "cost": float(payload.get("cost") or 0.0),
            "fms_residual_value": float(payload.get("fms_residual_value") or 0.0),
            "fms_currency_id": int(payload["fms_currency_id"]) if payload.get("fms_currency_id") else False,
            "fms_useful_life_months": int(payload["fms_useful_life_months"]) if payload.get("fms_useful_life_months") else False,
            "fms_depreciation_method": payload.get("fms_depreciation_method") or False,
            "fms_condition": payload.get("fms_condition") or "good",
            "fms_lifecycle_state": lifecycle,
        }
        equipment = self.env["maintenance.equipment"].create(vals)
        return {
            "id": equipment.id,
            "fms_asset_code": equipment.fms_asset_code,
            "name": equipment.name,
        }