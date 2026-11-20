# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.tools.translate import _


class FmsAssetDashboard(models.AbstractModel):
    _name = "fms.asset.dashboard"
    _description = "FMS Asset Dashboard"

    @api.model
    def get_dashboard_data(self, company=None):
        company = company or self.env.company
        equipment = self.env["maintenance.equipment"]
        if not equipment.has_access("read"):
            return {
                "available": False,
                "reason": _("You are not allowed to read assets."),
            }

        domain = [("company_id", "in", [company.id, False])]
        grouped = equipment.read_group(
            domain,
            ["fms_lifecycle_state"],
            ["fms_lifecycle_state"],
            lazy=False,
        )
        lifecycle_counts = {
            row.get("fms_lifecycle_state") or "unknown": row.get("__count", 0) for row in grouped
        }
        total_assets = sum(lifecycle_counts.values())
        classification_count = self.env["fms.asset.classification"].search_count(
            [("company_id", "=", company.id)]
        )
        location_count = self.env["fms.asset.location"].search_count([("company_id", "=", company.id)])
        company_domain = [("company_id", "in", [company.id, False])]
        warranty_expiring = 0
        amc_expiring = 0
        pending_transfers = 0
        pending_disposals = 0
        attention_health = 0
        if "fms.asset.warranty" in self.env:
            warranty_expiring = self.env["fms.asset.warranty"].search_count(
                company_domain + [("status", "=", "expiring")]
            )
        if "fms.asset.amc" in self.env:
            amc_expiring = self.env["fms.asset.amc"].search_count(
                company_domain + [("status", "=", "expiring")]
            )
        Transfer = self.env["fms.asset.transfer"]
        if Transfer.has_access("read"):
            pending_transfers = Transfer.search_count(company_domain + [("state", "=", "submitted")])
        Disposal = self.env["fms.asset.disposal"]
        if Disposal.has_access("read"):
            pending_disposals = Disposal.search_count(company_domain + [("state", "=", "submitted")])
        attention_health = equipment.search_count(
            domain + [("fms_health_status", "in", ["attention", "degraded"])]
        )
        depreciation_due_count = 0
        assets_without_schedule = 0
        total_book_value = 0.0
        today = fields.Date.context_today(self)
        if "fms.asset.depreciation.line" in self.env:
            depreciation_due_count = self.env["fms.asset.depreciation.line"].search_count(
                company_domain + [("state", "=", "pending"), ("period_date", "<=", today)]
            )
        if "fms.asset.depreciation.schedule" in self.env:
            eligible = equipment.search(
                domain
                + [
                    ("fms_lifecycle_state", "in", ["active", "under_maintenance", "inactive"]),
                    ("cost", ">", 0),
                ]
            )
            scheduled_equipment_ids = self.env["fms.asset.depreciation.schedule"].search(
                company_domain + [("state", "in", ("draft", "running"))]
            ).mapped("equipment_id").ids
            assets_without_schedule = len(eligible.filtered(lambda eq: eq.id not in scheduled_equipment_ids))
            total_book_value = sum(eligible.mapped("fms_book_value"))

        recent_assets = equipment.search_read(
            domain,
            ["fms_asset_code", "name", "fms_lifecycle_state", "fms_health_status", "write_date"],
            order="write_date desc, id desc",
            limit=6,
        )

        return {
            "available": True,
            "total_assets": total_assets,
            "recent_assets": recent_assets,
            "lifecycle_counts": lifecycle_counts,
            "active_assets": lifecycle_counts.get("active", 0),
            "under_maintenance": lifecycle_counts.get("under_maintenance", 0),
            "inactive_assets": lifecycle_counts.get("inactive", 0),
            "disposed_assets": lifecycle_counts.get("disposed", 0),
            "draft_assets": lifecycle_counts.get("draft", 0),
            "classification_count": classification_count,
            "location_count": location_count,
            "warranty_expiring": warranty_expiring,
            "amc_expiring": amc_expiring,
            "pending_transfers": pending_transfers,
            "pending_disposals": pending_disposals,
            "assets_requiring_attention": attention_health,
            "depreciation_due_count": depreciation_due_count,
            "assets_without_depreciation_schedule": assets_without_schedule,
            "total_book_value": total_book_value,
        }
