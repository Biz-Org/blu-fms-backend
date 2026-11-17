# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .mixins import FmsAssetWorkflowMixin


class FmsAssetTransfer(models.Model):
    _name = "fms.asset.transfer"
    _description = "FMS Asset Transfer"
    _inherit = ["mail.thread", "mail.activity.mixin", "fms.asset.workflow.mixin"]
    _order = "scheduled_transfer_date desc, id desc"
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
    transfer_type = fields.Selection(
        [("location", "Location"), ("custody", "Custody"), ("both", "Location & Custody")],
        default="location",
        required=True,
        tracking=True,
    )
    from_location_id = fields.Many2one("fms.asset.location", string="From Location", tracking=True)
    to_location_id = fields.Many2one("fms.asset.location", string="To Location", tracking=True)
    from_custodian_id = fields.Many2one("res.users", string="Current Custodian", tracking=True)
    to_custodian_id = fields.Many2one("res.users", string="New Custodian", tracking=True)
    scheduled_transfer_date = fields.Date(tracking=True, index=True)
    reason = fields.Text()
    requested_by_id = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        tracking=True,
    )
    responsible_user_id = fields.Many2one("res.users", string="Responsible User", tracking=True)
    notes = fields.Text()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("completed", "Completed"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    _fms_workflow_transitions = {
        "draft": {"submitted"},
        "submitted": {"approved", "rejected", "draft"},
        "approved": {"completed", "rejected"},
        "rejected": {"draft"},
        "completed": set(),
    }

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = seq.next_by_code("fms.asset.transfer") or "/"
        records = super().create(vals_list)
        for record in records:
            if record.equipment_id.fms_operations_locked:
                raise ValidationError(_("Cannot transfer a disposed asset."))
        return records

    def action_submit(self):
        self._fms_set_state("submitted")
        return True

    def action_approve(self):
        self._fms_set_state("approved")
        return True

    def action_reject(self):
        self._fms_set_state("rejected")
        return True

    def action_complete(self):
        for record in self:
            if record.state != "approved":
                raise ValidationError(_("Only approved transfers can be completed."))
            if record.equipment_id.fms_operations_locked:
                raise ValidationError(_("Cannot transfer a disposed asset."))
            if record.to_location_id:
                record.equipment_id.with_context(fms_allow_disposed_write=True).write(
                    {"fms_location_id": record.to_location_id.id}
                )
            if record.to_custodian_id:
                record.equipment_id.with_context(fms_allow_disposed_write=True).write(
                    {"owner_user_id": record.to_custodian_id.id}
                )
            record._fms_set_state("completed")
            record.equipment_id._fms_log_lifecycle_event(
                "transfer",
                _("Transfer completed: %(ref)s", ref=record.name),
                record.reason,
            )
        return True

    @api.model
    def fms_create_transfer(self, equipment_id, payload):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create transfers."))
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        if equipment.fms_operations_locked:
            raise ValidationError(_("Cannot transfer a disposed asset."))
        transfer = self.create(
            {
                "equipment_id": equipment.id,
                "transfer_type": payload.get("transfer_type") or "location",
                "from_location_id": equipment.fms_location_id.id if equipment.fms_location_id else False,
                "to_location_id": int(payload["to_location_id"]) if payload.get("to_location_id") else False,
                "from_custodian_id": equipment.owner_user_id.id if equipment.owner_user_id else False,
                "to_custodian_id": int(payload["to_custodian_id"]) if payload.get("to_custodian_id") else False,
                "scheduled_transfer_date": payload.get("scheduled_transfer_date") or fields.Date.context_today(self),
                "reason": payload.get("reason") or False,
                "notes": payload.get("notes") or False,
            }
        )
        if payload.get("submit"):
            transfer.action_submit()
        return {"id": transfer.id, "name": transfer.name, "state": transfer.state}