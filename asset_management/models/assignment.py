# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

ASSIGNMENT_TYPES = [
    ("employee", "Employee"),
    ("department", "Department"),
    ("team", "Team"),
    ("operations_group", "Facility Operations Group"),
]

ASSIGNMENT_STATES = [
    ("active", "Active"),
    ("returned", "Returned"),
]


class FmsAssetAssignmentHistory(models.Model):
    _name = "fms.asset.assignment.history"
    _description = "FMS Asset Assignment History"
    _order = "event_date desc, id desc"

    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    assignment_id = fields.Many2one("fms.asset.assignment", ondelete="set null", index=True)
    event_type = fields.Selection(
        [
            ("assigned", "Assigned"),
            ("returned", "Returned"),
            ("reassigned", "Reassigned"),
        ],
        required=True,
        default="assigned",
    )
    event_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    assignment_type = fields.Selection(ASSIGNMENT_TYPES)
    assigned_user_id = fields.Many2one("res.users", index=True)
    department = fields.Char(index=True)
    location_id = fields.Many2one("fms.asset.location", index=True)
    performed_by_id = fields.Many2one(
        "res.users",
        string="Recorded By",
        default=lambda self: self.env.user,
        required=True,
    )
    notes = fields.Text()


class FmsAssetAssignment(models.Model):
    _name = "fms.asset.assignment"
    _description = "FMS Asset Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "assignment_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    assignment_type = fields.Selection(ASSIGNMENT_TYPES, required=True, default="employee", tracking=True)
    assigned_user_id = fields.Many2one("res.users", string="Assigned To", tracking=True, index=True)
    department = fields.Char(string="Department", tracking=True, index=True)
    location_id = fields.Many2one(
        "fms.asset.location",
        string="Assignment Location",
        domain="[('location_type', '=', 'room')]",
        tracking=True,
    )
    assignment_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    expected_return_date = fields.Date(tracking=True)
    acknowledgement_required = fields.Boolean(default=False)
    acknowledgement_due_date = fields.Date()
    state = fields.Selection(ASSIGNMENT_STATES, default="active", required=True, tracking=True, index=True)
    notes = fields.Text()
    history_ids = fields.One2many("fms.asset.assignment.history", "assignment_id")

    @api.depends("equipment_id", "assignment_type", "assigned_user_id", "department")
    def _compute_name(self):
        for record in self:
            asset = record.equipment_id.display_name or _("Asset")
            if record.assignment_type == "employee" and record.assigned_user_id:
                target = record.assigned_user_id.name
            elif record.department:
                target = record.department
            else:
                target = dict(ASSIGNMENT_TYPES).get(record.assignment_type, "")
            record.name = f"{asset} → {target}"

    @api.constrains("equipment_id", "state")
    def _check_disposed_equipment(self):
        for record in self:
            if record.state == "active" and record.equipment_id.fms_operations_locked:
                raise ValidationError(_("Cannot assign a disposed asset."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fms_activate_assignment()
        return records

    def _fms_activate_assignment(self):
        Equipment = self.env["maintenance.equipment"]
        for record in self:
            if record.state != "active":
                continue
            others = self.search(
                [
                    ("equipment_id", "=", record.equipment_id.id),
                    ("state", "=", "active"),
                    ("id", "!=", record.id),
                ]
            )
            for other in others:
                other._fms_return(notify=False)
            if record.assigned_user_id:
                record.equipment_id.with_context(fms_allow_disposed_write=True).write(
                    {"owner_user_id": record.assigned_user_id.id}
                )
            record._fms_log_history("assigned")
            record.equipment_id._fms_log_lifecycle_event(
                "assignment",
                _("Custody assigned: %(name)s", name=record.name),
            )

    def action_return(self):
        self._fms_return(notify=True)
        return True

    def _fms_return(self, notify=True):
        for record in self.filtered(lambda r: r.state == "active"):
            record.write({"state": "returned"})
            record._fms_log_history("returned")
            record.equipment_id._fms_log_lifecycle_event(
                "assignment",
                _("Custody returned for %(asset)s", asset=record.equipment_id.display_name),
            )
            if notify:
                record.message_post(body=_("Assignment returned."))

    def _fms_log_history(self, event_type):
        if not self.env["fms.asset.assignment.history"].has_access("create"):
            return
        for record in self:
            self.env["fms.asset.assignment.history"].sudo().create(
                {
                    "equipment_id": record.equipment_id.id,
                    "assignment_id": record.id,
                    "event_type": event_type,
                    "assignment_type": record.assignment_type,
                    "assigned_user_id": record.assigned_user_id.id if record.assigned_user_id else False,
                    "department": record.department,
                    "location_id": record.location_id.id if record.location_id else False,
                    "notes": record.notes,
                }
            )

    @api.model
    def fms_create_assignment(self, equipment_id, payload):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create assignments."))
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        equipment.check_access("write")
        if equipment.fms_operations_locked:
            raise ValidationError(_("Disposed assets cannot be assigned."))
        assignment = self.create(
            {
                "equipment_id": equipment.id,
                "assignment_type": payload.get("assignment_type") or "employee",
                "assigned_user_id": int(payload["assigned_user_id"]) if payload.get("assigned_user_id") else False,
                "department": (payload.get("department") or "").strip() or False,
                "location_id": int(payload["location_id"]) if payload.get("location_id") else False,
                "assignment_date": payload.get("assignment_date") or fields.Date.context_today(self),
                "expected_return_date": payload.get("expected_return_date") or False,
                "acknowledgement_required": bool(payload.get("acknowledgement_required")),
                "acknowledgement_due_date": payload.get("acknowledgement_due_date") or False,
                "notes": payload.get("notes") or False,
            }
        )
        return {"id": assignment.id, "name": assignment.name}