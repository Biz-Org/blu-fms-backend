# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools.translate import _


class FmsAssetAccountingConfig(models.Model):
    _name = "fms.asset.accounting.config"
    _description = "FMS Asset Accounting Bridge (per company)"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
        index=True,
    )
    auto_post_journal = fields.Boolean(
        string="Post GL on Depreciation",
        help="When the Accounting app is installed, posted depreciation lines can "
        "generate draft journal entries using the accounts below (matched by code).",
    )
    depreciation_expense_account_code = fields.Char(string="Depreciation Expense Account Code")
    accumulated_depreciation_account_code = fields.Char(string="Accumulated Depreciation Account Code")
    journal_code = fields.Char(
        string="Journal Code",
        default="MISC",
        help="Journal code used for auto-generated entries (default: MISC).",
    )
    notes = fields.Text(help="Internal notes for finance administrators.")

    _sql_constraints = [
        (
            "fms_asset_accounting_config_company_uniq",
            "unique(company_id)",
            "Only one accounting bridge configuration per company.",
        ),
    ]