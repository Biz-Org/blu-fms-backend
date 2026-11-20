# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .constants import LOCATION_TYPES


class FmsAssetLocation(models.Model):
    _name = "fms.asset.location"
    _description = "FMS Asset Location"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "location_type, complete_name"
    _rec_name = "complete_name"

    name = fields.Char(required=True, index=True, translate=True)
    code = fields.Char(index=True)
    location_type = fields.Selection(LOCATION_TYPES, required=True, index=True)
    parent_id = fields.Many2one(
        "fms.asset.location",
        string="Parent Location",
        ondelete="cascade",
        index=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("fms.asset.location", "parent_id")
    complete_name = fields.Char(compute="_compute_complete_name", store=True, recursive=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    description = fields.Text()
    equipment_ids = fields.One2many(
        "maintenance.equipment",
        "fms_location_id",
        string="Assets",
    )
    equipment_count = fields.Integer(compute="_compute_equipment_count")
    fms_core_location_ref = fields.Char(
        string="FMS Core Location Ref",
        help="FUTURE: integration key for fms_core.fms.location when a bridge module is installed.",
    )

    _sql_constraints = [
        (
            "fms_asset_location_code_company_uniq",
            "unique(code, company_id)",
            "Location code must be unique per company.",
        ),
    ]

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = f"{record.parent_id.complete_name} / {record.name}"
            else:
                record.complete_name = record.name

    @api.depends("equipment_ids")
    def _compute_equipment_count(self):
        for record in self:
            record.equipment_count = len(record.equipment_ids)

    @api.model
    def fms_search_locations(self, term="", limit=30):
        if not self.has_access("read"):
            return []
        domain = [("active", "=", True), ("location_type", "=", "room")]
        if term:
            domain += ["|", ("name", "ilike", term), ("code", "ilike", term)]
        locations = self.search(domain, limit=int(limit or 30))
        return [{"id": loc.id, "label": loc.complete_name} for loc in locations]

    @api.constrains("parent_id", "location_type")
    def _check_parent_type(self):
        expectations = {
            "property": (None, None),
            "building": ("property", "Property / Site"),
            "floor": ("building", "Building / Tower"),
            "wing_area": ("floor", "Floor"),
            "room": ("wing_area", "Wing / Area"),
        }
        for record in self:
            expected_parent, label = expectations[record.location_type]
            if record.location_type == "property":
                if record.parent_id:
                    raise ValidationError(_("A property cannot have a parent location."))
                continue
            if not record.parent_id or record.parent_id.location_type != expected_parent:
                raise ValidationError(
                    _("%(type)s must belong to a %(parent)s.", type=record.location_type, parent=label)
                )
            if record.parent_id.company_id != record.company_id:
                raise ValidationError(_("Parent location must belong to the same company."))
