# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .mixins import FmsAssetWorkflowMixin


class FmsAssetDisposal(models.Model):
    _name = "fms.asset.disposal"
    _description = "FMS Asset Disposal"
    _inherit = ["mail.thread", "mail.activity.mixin", "fms.asset.workflow.mixin"]
    _order = "disposal_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, default="/", index=True, tracking=True)
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    disposal_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    disposal_reason = fields.Selection(
        [
            ("end_of_life", "End of Life"),
            ("damaged", "Damaged Beyond Repair"),
            ("obsolete", "Obsolete"),
            ("sold", "Sold"),
            ("other", "Other"),
        ],
        required=True,
        tracking=True,
    )
    disposal_method = fields.Char(tracking=True)
    book_value = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    remarks = fields.Text()
    requested_by_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("disposed", "Disposed"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    _fms_workflow_transitions = {
        "draft": {"submitted"},
        "submitted": {"approved", "rejected", "draft"},
        "approved": {"disposed", "rejected"},
        "rejected": {"draft"},
        "disposed": set(),
    }

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = seq.next_by_code("fms.asset.disposal") or "/"
        records = super().create(vals_list)
        for record in records:
            if record.equipment_id.fms_lifecycle_state == "disposed":
                raise ValidationError(_("Asset is already disposed."))
        return records

    def action_submit(self):
        self._fms_set_state("submitted")
        return True

    def action_approve(self):
        for record in self:
            record.write({"approved_by_id": self.env.user.id})
            record._fms_set_state("approved")
        return True

    def action_reject(self):
        self._fms_set_state("rejected")
        return True

    def action_dispose(self):
        for record in self:
            if record.state != "approved":
                raise ValidationError(_("Only approved disposal requests can be finalized."))
            equipment = record.equipment_id
            active_assignments = self.env["fms.asset.assignment"].search(
                [("equipment_id", "=", equipment.id), ("state", "=", "active")]
            )
            for assignment in active_assignments:
                assignment.action_return()
            equipment.with_context(fms_allow_disposed_write=True).write(
                {"fms_lifecycle_state": "disposed"}
            )
            record._fms_set_state("disposed")
            equipment._fms_log_lifecycle_event(
                "disposal",
                _("Disposal completed: %(ref)s", ref=record.name),
                record.remarks,
            )
        return True

    @api.model
    def fms_create_disposal(self, equipment_id, payload):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create disposal records."))
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        if equipment.fms_lifecycle_state == "disposed":
            raise ValidationError(_("Asset is already disposed."))
        default_book = equipment.fms_book_value if equipment.fms_book_value is not None else equipment.cost
        disposal = self.create(
            {
                "equipment_id": equipment.id,
                "disposal_date": payload.get("disposal_date") or fields.Date.context_today(self),
                "disposal_reason": payload.get("disposal_reason") or "other",
                "disposal_method": payload.get("disposal_method") or False,
                "book_value": float(payload.get("book_value") if payload.get("book_value") is not None else default_book or 0.0),
                "remarks": payload.get("remarks") or False,
            }
        )
        if payload.get("submit"):
            disposal.action_submit()
        return {"id": disposal.id, "name": disposal.name, "state": disposal.state}