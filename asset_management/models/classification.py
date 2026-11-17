# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

from .constants import CLASSIFICATION_LEVELS, CRITICALITY_LEVELS, DEPRECIATION_METHODS


class FmsAssetClassification(models.Model):
    _name = "fms.asset.classification"
    _description = "FMS Asset Classification"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "level, complete_name"
    _rec_name = "complete_name"

    name = fields.Char(required=True, index=True, translate=True)
    code = fields.Char(index=True)
    level = fields.Selection(
        CLASSIFICATION_LEVELS,
        required=True,
        index=True,
    )
    parent_id = fields.Many2one(
        "fms.asset.classification",
        string="Parent",
        ondelete="cascade",
        index=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("fms.asset.classification", "parent_id")
    complete_name = fields.Char(compute="_compute_complete_name", store=True, recursive=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    equipment_ids = fields.One2many(
        "maintenance.equipment",
        "fms_classification_id",
        string="Assets",
    )
    equipment_count = fields.Integer(compute="_compute_equipment_count")

    maintenance_category_id = fields.Many2one(
        "maintenance.equipment.category",
        string="Maintenance Category (optional)",
        help="Optional link to Odoo maintenance equipment category. "
        "Does not restrict the FMS classification hierarchy.",
        ondelete="set null",
    )

    default_criticality = fields.Selection(CRITICALITY_LEVELS, default="medium")
    default_useful_life_months = fields.Integer(string="Default Useful Life (months)")
    default_depreciation_method = fields.Selection(
        DEPRECIATION_METHODS,
        string="Default Depreciation Method",
        help="Stored for reference only until Phase 5 accounting integration.",
    )
    default_inspection_frequency_days = fields.Integer(
        string="Default Inspection Frequency (days)",
    )
    requires_warranty = fields.Boolean(string="Warranty Required", default=False)
    requires_amc = fields.Boolean(string="AMC Required", default=False)
    description = fields.Html(translate=True)

    _sql_constraints = [
        (
            "fms_asset_classification_code_company_uniq",
            "unique(code, company_id)",
            "Classification code must be unique per company.",
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

    @api.constrains("parent_id", "level")
    def _check_parent_level(self):
        parent_expectations = {
            "category": (None, None),
            "type": ("category", "Category"),
            "subtype": ("type", "Asset Type"),
        }
        for record in self:
            expected_parent, label = parent_expectations[record.level]
            if record.level == "category":
                if record.parent_id:
                    raise ValidationError(_("A category cannot have a parent."))
                continue
            if not record.parent_id or record.parent_id.level != expected_parent:
                raise ValidationError(
                    _("%(level)s must belong to a %(parent)s.", level=record.level, parent=label)
                )
            if record.parent_id.company_id != record.company_id:
                raise ValidationError(_("Parent classification must belong to the same company."))

    @api.constrains("child_ids", "equipment_ids")
    def _check_leaf_assignment(self):
        for record in self:
            if record.child_ids and record.equipment_ids:
                raise ValidationError(
                    _("Assets can only be assigned to leaf classifications (sub-types).")
                )
            if record.equipment_ids and record.level != "subtype":
                raise ValidationError(_("Assets must be assigned to a sub-type classification."))
