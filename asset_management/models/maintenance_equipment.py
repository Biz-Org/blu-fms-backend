# -*- coding: utf-8 -*-

import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .constants import (
    CONDITION_STATES,
    DEPRECIATION_METHODS,
    HEALTH_STATUSES,
    LIFECYCLE_STATES,
)


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    fms_asset_code = fields.Char(
        string="Asset ID",
        copy=False,
        index=True,
        readonly=True,
        tracking=True,
    )
    fms_classification_id = fields.Many2one(
        "fms.asset.classification",
        string="FMS Classification",
        tracking=True,
        index=True,
        check_company=True,
    )
    fms_location_id = fields.Many2one(
        "fms.asset.location",
        string="FMS Location",
        tracking=True,
        index=True,
        check_company=True,
    )
    fms_lifecycle_state = fields.Selection(
        LIFECYCLE_STATES,
        string="Lifecycle Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    fms_condition = fields.Selection(
        CONDITION_STATES,
        string="Condition",
        default="good",
        tracking=True,
    )
    fms_health_status = fields.Selection(
        HEALTH_STATUSES,
        string="Health Status",
        default="unknown",
        tracking=True,
        index=True,
    )
    fms_manufacturer = fields.Char(string="Manufacturer", tracking=True)
    fms_image = fields.Image(string="Asset Image", max_width=1920, max_height=1920)
    fms_acquisition_date = fields.Date(string="Acquisition Date")
    fms_residual_value = fields.Monetary(string="Residual Value", currency_field="fms_currency_id")
    fms_useful_life_months = fields.Integer(
        string="Useful Life (months)",
        help="Used when generating FMS depreciation schedules.",
    )
    fms_depreciation_method = fields.Selection(
        DEPRECIATION_METHODS,
        string="Depreciation Method",
        help="Depreciation method for FMS schedules (see Financial tab).",
    )
    fms_currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    fms_operations_locked = fields.Boolean(
        string="Operations Locked",
        compute="_compute_fms_operations_locked",
        help="True when lifecycle is disposed. New assignments, transfers and "
        "operational maintenance are blocked in later phases.",
    )
    fms_property_integration_ref = fields.Char(
        string="Property Integration Ref",
        help="FUTURE: link to Property Management (#2) or fms_core location.",
    )
    fms_purchase_order_ref = fields.Char(string="Purchase Order Reference", tracking=True)
    fms_invoice_ref = fields.Char(string="Invoice Reference", tracking=True)
    fms_assignment_ids = fields.One2many("fms.asset.assignment", "equipment_id")
    fms_current_assignment_id = fields.Many2one(
        "fms.asset.assignment",
        compute="_compute_fms_current_assignment",
        store=True,
        string="Current Assignment",
    )
    fms_assignment_history_ids = fields.One2many(
        "fms.asset.assignment.history",
        "equipment_id",
        string="Assignment History",
    )
    fms_lifecycle_event_ids = fields.One2many("fms.asset.lifecycle.event", "equipment_id")
    fms_document_count = fields.Integer(compute="_compute_fms_document_count")
    fms_qr_token = fields.Char(copy=False, index=True, tracking=True)
    fms_barcode = fields.Char(copy=False, index=True, tracking=True)
    fms_warranty_ids = fields.One2many("fms.asset.warranty", "equipment_id")
    fms_amc_ids = fields.One2many("fms.asset.amc", "equipment_id")
    fms_inspection_ids = fields.One2many("fms.asset.inspection", "equipment_id")
    fms_transfer_ids = fields.One2many("fms.asset.transfer", "equipment_id")
    fms_disposal_ids = fields.One2many("fms.asset.disposal", "equipment_id")
    fms_depreciation_schedule_ids = fields.One2many("fms.asset.depreciation.schedule", "equipment_id")
    fms_active_depreciation_schedule_id = fields.Many2one(
        "fms.asset.depreciation.schedule",
        string="Active Depreciation Schedule",
        compute="_compute_fms_depreciation_financials",
        store=True,
    )
    fms_accumulated_depreciation = fields.Monetary(
        string="Accumulated Depreciation",
        compute="_compute_fms_depreciation_financials",
        store=True,
        currency_field="fms_currency_id",
    )
    fms_book_value = fields.Monetary(
        string="Book Value",
        compute="_compute_fms_depreciation_financials",
        store=True,
        currency_field="fms_currency_id",
    )
    fms_health_score = fields.Float(compute="_compute_fms_health_score", store=True)

    @api.depends(
        "fms_depreciation_schedule_ids",
        "fms_depreciation_schedule_ids.state",
        "fms_depreciation_schedule_ids.book_value",
        "fms_depreciation_schedule_ids.accumulated_depreciation",
        "cost",
        "fms_residual_value",
    )
    def _compute_fms_depreciation_financials(self):
        for record in self:
            schedule = record.fms_depreciation_schedule_ids.filtered(
                lambda sched: sched.state in ("draft", "running")
            )[:1]
            if not schedule:
                schedule = record.fms_depreciation_schedule_ids[:1]
            record.fms_active_depreciation_schedule_id = schedule
            if schedule:
                record.fms_accumulated_depreciation = schedule.accumulated_depreciation
                record.fms_book_value = schedule.book_value
            else:
                record.fms_accumulated_depreciation = 0.0
                record.fms_book_value = record.cost or 0.0

    @api.depends("fms_inspection_ids", "fms_inspection_ids.state", "fms_inspection_ids.health_score")
    def _compute_fms_health_score(self):
        for record in self:
            inspections = record.fms_inspection_ids.filtered(lambda i: i.state == "completed")
            latest = inspections[:1]
            record.fms_health_score = latest.health_score if latest else 0.0

    @api.depends("fms_assignment_ids", "fms_assignment_ids.state")
    def _compute_fms_current_assignment(self):
        for record in self:
            active = record.fms_assignment_ids.filtered(lambda a: a.state == "active")[:1]
            record.fms_current_assignment_id = active

    def _compute_fms_document_count(self):
        attachment = self.env["ir.attachment"]
        for record in self:
            if attachment.has_access("read"):
                record.fms_document_count = attachment.search_count(
                    [
                        ("res_model", "=", self._name),
                        ("res_id", "=", record.id),
                    ]
                )
            else:
                record.fms_document_count = 0

    _sql_constraints = [
        (
            "fms_asset_code_company_uniq",
            "unique(fms_asset_code, company_id)",
            "Asset ID must be unique per company.",
        ),
        (
            "fms_qr_token_company_uniq",
            "unique(fms_qr_token, company_id)",
            "QR token must be unique per company.",
        ),
        (
            "fms_barcode_company_uniq",
            "unique(fms_barcode, company_id)",
            "Barcode must be unique per company.",
        ),
    ]

    @api.depends("fms_lifecycle_state")
    def _compute_fms_operations_locked(self):
        for record in self:
            record.fms_operations_locked = record.fms_lifecycle_state == "disposed"

    @api.constrains("fms_classification_id", "company_id")
    def _check_classification_company(self):
        for record in self:
            if record.fms_classification_id and record.fms_classification_id.level != "subtype":
                raise ValidationError(_("Assets must be assigned to a sub-type classification."))
            if (
                record.fms_classification_id
                and record.company_id
                and record.fms_classification_id.company_id != record.company_id
            ):
                raise ValidationError(_("FMS classification must belong to the same company as the asset."))

    @api.constrains("fms_location_id", "company_id")
    def _check_location_company(self):
        for record in self:
            if (
                record.fms_location_id
                and record.company_id
                and record.fms_location_id.company_id != record.company_id
            ):
                raise ValidationError(_("FMS location must belong to the same company as the asset."))

    def _fms_disposed_write_blocked_fields(self):
        return {
            "fms_location_id",
            "fms_classification_id",
            "owner_user_id",
            "fms_lifecycle_state",
        }

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("fms_asset_code"):
                vals["fms_asset_code"] = sequence.next_by_code("fms.asset.code") or "/"
            if not vals.get("serial_no"):
                vals["serial_no"] = vals["fms_asset_code"]
            if vals.get("fms_classification_id") and not vals.get("category_id"):
                classification = self.env["fms.asset.classification"].browse(
                    vals["fms_classification_id"]
                )
                if classification.maintenance_category_id:
                    vals["category_id"] = classification.maintenance_category_id.id
        records = super().create(vals_list)
        records._fms_sync_location_char()
        records._fms_ensure_qr_token()
        records._fms_log_lifecycle_event("registration", _("Asset registered."))
        return records

    def write(self, vals):
        if not self.env.context.get("fms_allow_disposed_write"):
            blocked = self._fms_disposed_write_blocked_fields() & set(vals.keys())
            if blocked:
                disposed = self.filtered(lambda r: r.fms_lifecycle_state == "disposed")
                if disposed:
                    raise ValidationError(
                        _(
                            "Disposed assets cannot change operational master data (%(fields)s). "
                            "Archiving is a separate authorised action.",
                            fields=", ".join(sorted(blocked)),
                        )
                    )
        if "fms_classification_id" in vals and "category_id" not in vals:
            classification = self.env["fms.asset.classification"].browse(
                vals.get("fms_classification_id")
            )
            if classification.maintenance_category_id:
                vals["category_id"] = classification.maintenance_category_id.id
        result = super().write(vals)
        if "fms_location_id" in vals:
            self._fms_sync_location_char()
            for record in self:
                record._fms_log_lifecycle_event("location", _("Location updated."))
        if "fms_classification_id" in vals:
            for record in self:
                record._fms_log_lifecycle_event("classification", _("Classification updated."))
        if "fms_lifecycle_state" in vals:
            for record in self:
                record._fms_log_lifecycle_event(
                    "status",
                    _("Lifecycle status set to %(state)s", state=record.fms_lifecycle_state),
                )
        return result

    def _fms_sync_location_char(self):
        for record in self:
            location_label = (
                record.fms_location_id.complete_name if record.fms_location_id else record.location
            )
            if record.location != location_label:
                super(
                    MaintenanceEquipment,
                    record.with_context(fms_allow_disposed_write=True),
                ).write({"location": location_label})

    def action_fms_set_disposed(self):
        """Lifecycle helper for tests and future disposal workflow (does not archive)."""
        self._fms_validate_disposal_transition()
        self.with_context(fms_allow_disposed_write=True).write({"fms_lifecycle_state": "disposed"})
        self._fms_log_lifecycle_event("disposal", _("Asset marked as disposed."))
        return True

    def _fms_validate_disposal_transition(self):
        for record in self:
            if record.fms_lifecycle_state == "disposed":
                raise ValidationError(_("Asset is already disposed."))

    def _fms_log_lifecycle_event(self, event_type, summary, details=False):
        if not self.env["fms.asset.lifecycle.event"].has_access("create"):
            return
        for record in self:
            self.env["fms.asset.lifecycle.event"].sudo().create(
                {
                    "equipment_id": record.id,
                    "event_type": event_type,
                    "summary": summary,
                    "details": details or False,
                }
            )

    @api.model
    def fms_get_register_domain(
        self, search_term=False, lifecycle=False, classification_id=False, location_id=False
    ):
        domain = []
        if search_term:
            term = search_term.strip()
            domain += [
                "|",
                "|",
                ("name", "ilike", term),
                ("fms_asset_code", "ilike", term),
                ("serial_no", "ilike", term),
            ]
        if lifecycle:
            domain.append(("fms_lifecycle_state", "=", lifecycle))
        if classification_id:
            domain.append(("fms_classification_id", "=", int(classification_id)))
        if location_id:
            domain.append(("fms_location_id", "=", int(location_id)))
        return domain

    @api.model
    def fms_get_detail_payload_by_id(self, equipment_id):
        record = self.browse(int(equipment_id))
        record.check_access("read")
        return record.fms_get_detail_payload()

    def fms_get_detail_payload(self):
        self.ensure_one()
        active_assignment = self.fms_current_assignment_id
        return {
            "id": self.id,
            "fms_asset_code": self.fms_asset_code,
            "name": self.name,
            "model": self.model,
            "serial_no": self.serial_no,
            "fms_manufacturer": self.fms_manufacturer,
            "fms_lifecycle_state": self.fms_lifecycle_state,
            "fms_condition": self.fms_condition,
            "fms_health_status": self.fms_health_status,
            "fms_operations_locked": self.fms_operations_locked,
            "fms_classification_id": self._fms_pair(self.fms_classification_id),
            "fms_location_id": self._fms_pair(self.fms_location_id),
            "location": self.location,
            "owner_user_id": self._fms_pair(self.owner_user_id),
            "partner_id": self._fms_pair(self.partner_id),
            "fms_acquisition_date": fields.Date.to_string(self.fms_acquisition_date) if self.fms_acquisition_date else False,
            "fms_purchase_order_ref": self.fms_purchase_order_ref,
            "fms_invoice_ref": self.fms_invoice_ref,
            "cost": self.cost,
            "fms_residual_value": self.fms_residual_value,
            "fms_useful_life_months": self.fms_useful_life_months,
            "fms_depreciation_method": self.fms_depreciation_method,
            "fms_accumulated_depreciation": self.fms_accumulated_depreciation,
            "fms_book_value": self.fms_book_value,
            "depreciation": self.fms_active_depreciation_schedule_id
            and self.fms_active_depreciation_schedule_id.fms_get_schedule_payload(),
            "fms_currency_id": self._fms_pair(self.fms_currency_id),
            "fms_document_count": self.fms_document_count,
            "note": self.note,
            "assignment": active_assignment
            and {
                "id": active_assignment.id,
                "assignment_type": active_assignment.assignment_type,
                "assigned_user_id": self._fms_pair(active_assignment.assigned_user_id),
                "department": active_assignment.department,
                "assignment_date": fields.Date.to_string(active_assignment.assignment_date)
                if active_assignment.assignment_date
                else False,
                "expected_return_date": fields.Date.to_string(active_assignment.expected_return_date)
                if active_assignment.expected_return_date
                else False,
            },
            "assignment_history": [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "event_date": fields.Datetime.to_string(row.event_date),
                    "assignment_type": row.assignment_type,
                    "assigned_user_id": self._fms_pair(row.assigned_user_id),
                    "department": row.department,
                    "notes": row.notes,
                }
                for row in self.fms_assignment_history_ids[:20]
            ],
            "lifecycle_events": [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "event_date": fields.Datetime.to_string(row.event_date),
                    "summary": row.summary,
                    "user_id": self._fms_pair(row.user_id),
                }
                for row in self.fms_lifecycle_event_ids[:30]
            ],
            "fms_qr_token": self.fms_qr_token,
            "fms_barcode": self.fms_barcode,
            "fms_health_score": self.fms_health_score,
            "warranties": [
                {
                    "id": w.id,
                    "name": w.name,
                    "status": w.status,
                    "end_date": fields.Date.to_string(w.end_date) if w.end_date else False,
                }
                for w in self.fms_warranty_ids[:10]
            ],
            "amc_contracts": [
                {
                    "id": a.id,
                    "name": a.name,
                    "status": a.status,
                    "contract_end_date": fields.Date.to_string(a.contract_end_date)
                    if a.contract_end_date
                    else False,
                }
                for a in self.fms_amc_ids[:10]
            ],
            "inspections": [
                {
                    "id": i.id,
                    "name": i.name,
                    "state": i.state,
                    "inspection_date": fields.Datetime.to_string(i.inspection_date),
                    "health_status": i.health_status,
                    "condition": i.condition,
                }
                for i in self.fms_inspection_ids[:10]
            ],
            "transfers": [
                {
                    "id": t.id,
                    "name": t.name,
                    "state": t.state,
                    "scheduled_transfer_date": fields.Date.to_string(t.scheduled_transfer_date)
                    if t.scheduled_transfer_date
                    else False,
                }
                for t in self.fms_transfer_ids[:10]
            ],
            "disposals": [
                {
                    "id": d.id,
                    "name": d.name,
                    "state": d.state,
                    "disposal_date": fields.Date.to_string(d.disposal_date) if d.disposal_date else False,
                }
                for d in self.fms_disposal_ids[:10]
            ],
        }

    def _fms_pair(self, record):
        return record and [record.id, record.display_name] or False

    def _fms_ensure_qr_token(self):
        for record in self.filtered(lambda r: not r.fms_qr_token):
            record.with_context(fms_allow_disposed_write=True).write(
                {"fms_qr_token": record._fms_new_qr_token()}
            )

    def _fms_new_qr_token(self):
        return secrets.token_urlsafe(16)

    def action_fms_regenerate_qr(self):
        for record in self:
            if record.fms_operations_locked:
                raise ValidationError(_("Cannot change QR code on a disposed asset."))
            record.with_context(fms_allow_disposed_write=True).write(
                {"fms_qr_token": record._fms_new_qr_token()}
            )
            record._fms_log_lifecycle_event("registration", _("QR token regenerated."))
        return True

    @api.model
    def fms_resolve_qr_token(self, token):
        token = (token or "").strip()
        if not token:
            raise ValidationError(_("QR token is required."))
        equipment = self.search([("fms_qr_token", "=", token)], limit=1)
        if not equipment:
            equipment = self.search([("fms_barcode", "=", token)], limit=1)
        if not equipment:
            raise ValidationError(_("No asset found for this code."))
        equipment.check_access("read")
        return {"id": equipment.id, "fms_asset_code": equipment.fms_asset_code, "name": equipment.name}

    @api.model
    def fms_search_assignable_users(self, term="", limit=20):
        if not self.env["res.users"].has_access("read"):
            return []
        domain = [("share", "=", False)]
        if term:
            domain += ["|", ("name", "ilike", term), ("login", "ilike", term)]
        users = self.env["res.users"].search(domain, limit=int(limit or 20))
        return [{"id": user.id, "label": user.display_name} for user in users]

    @api.model
    def fms_generate_qr_batch(self, equipment_ids):
        if not self.has_access("write"):
            raise ValidationError(_("You are not allowed to generate QR tokens."))
        records = self.browse(equipment_ids).exists()
        records.action_fms_regenerate_qr()
        return [{"id": r.id, "fms_qr_token": r.fms_qr_token} for r in records]
