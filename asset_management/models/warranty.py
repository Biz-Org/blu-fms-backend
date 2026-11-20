# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class FmsAssetWarranty(models.Model):
    _name = "fms.asset.warranty"
    _description = "FMS Asset Warranty"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "end_date desc, id desc"
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
    provider_id = fields.Many2one("res.partner", string="Warranty Provider", tracking=True)
    reference = fields.Char(tracking=True)
    start_date = fields.Date(tracking=True, index=True)
    end_date = fields.Date(tracking=True, index=True)
    coverage_details = fields.Html()
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("expiring", "Expiring Soon"),
            ("expired", "Expired"),
        ],
        compute="_compute_status",
        store=True,
        index=True,
    )

    @api.depends("start_date", "end_date")
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.end_date:
                record.status = "draft"
            elif record.end_date < today:
                record.status = "expired"
            elif (record.end_date - today).days <= 30:
                record.status = "expiring"
            elif record.start_date and record.start_date > today:
                record.status = "draft"
            else:
                record.status = "active"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.equipment_id._fms_log_lifecycle_event(
                "warranty",
                _("Warranty recorded: %(name)s", name=record.name),
            )
        return records

    @api.model
    def fms_create_warranty(self, equipment_id, payload):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create warranty records."))
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        if equipment.fms_operations_locked:
            raise ValidationError(_("Cannot add warranty to a disposed asset."))
        warranty = self.create(
            {
                "name": payload.get("name") or _("Warranty"),
                "equipment_id": equipment.id,
                "provider_id": int(payload["provider_id"]) if payload.get("provider_id") else False,
                "reference": payload.get("reference") or False,
                "start_date": payload.get("start_date") or False,
                "end_date": payload.get("end_date") or False,
                "coverage_details": payload.get("coverage_details") or False,
            }
        )
        return {"id": warranty.id, "status": warranty.status}

    @api.model
    def cron_refresh_fms_contract_status(self):
        self.search([])._compute_status()
        self.env["fms.asset.amc"].search([])._compute_status()
        return True