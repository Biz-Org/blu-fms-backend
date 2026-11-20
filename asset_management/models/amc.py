# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class FmsAssetAmc(models.Model):
    _name = "fms.asset.amc"
    _description = "FMS Asset AMC Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "contract_end_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Contract Number", required=True, tracking=True)
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor", tracking=True)
    amc_type = fields.Char(tracking=True)
    contract_start_date = fields.Date(tracking=True, index=True)
    contract_end_date = fields.Date(tracking=True, index=True)
    service_frequency = fields.Char()
    planned_visits_per_year = fields.Integer()
    contract_value = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    payment_frequency = fields.Char()
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

    @api.depends("contract_start_date", "contract_end_date")
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.contract_end_date:
                record.status = "draft"
            elif record.contract_end_date < today:
                record.status = "expired"
            elif (record.contract_end_date - today).days <= 30:
                record.status = "expiring"
            elif record.contract_start_date and record.contract_start_date > today:
                record.status = "draft"
            else:
                record.status = "active"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.equipment_id._fms_log_lifecycle_event(
                "warranty",
                _("AMC contract recorded: %(name)s", name=record.name),
            )
        return records

    @api.model
    def fms_create_amc(self, equipment_id, payload):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create AMC records."))
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        if equipment.fms_operations_locked:
            raise ValidationError(_("Cannot add AMC to a disposed asset."))
        amc = self.create(
            {
                "name": payload.get("name") or _("AMC"),
                "equipment_id": equipment.id,
                "vendor_id": int(payload["vendor_id"]) if payload.get("vendor_id") else False,
                "amc_type": payload.get("amc_type") or False,
                "contract_start_date": payload.get("contract_start_date") or False,
                "contract_end_date": payload.get("contract_end_date") or False,
                "service_frequency": payload.get("service_frequency") or False,
                "planned_visits_per_year": int(payload["planned_visits_per_year"])
                if payload.get("planned_visits_per_year")
                else False,
                "contract_value": float(payload.get("contract_value") or 0.0),
            }
        )
        return {"id": amc.id, "status": amc.status}