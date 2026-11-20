# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round
from odoo.tools.translate import _

from .constants import DEPRECIATION_METHODS

SCHEDULE_STATES = [
    ("draft", "Draft"),
    ("running", "Running"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

LINE_STATES = [
    ("pending", "Pending"),
    ("posted", "Posted"),
    ("skipped", "Skipped"),
]


class FmsAssetDepreciationSchedule(models.Model):
    _name = "fms.asset.depreciation.schedule"
    _description = "FMS Asset Depreciation Schedule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Depreciation Schedule"))
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(related="equipment_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="equipment_id.fms_currency_id", store=True)
    state = fields.Selection(SCHEDULE_STATES, default="draft", required=True, tracking=True, index=True)
    method = fields.Selection(DEPRECIATION_METHODS, required=True, tracking=True)
    acquisition_cost = fields.Monetary(currency_field="currency_id", required=True)
    residual_value = fields.Monetary(currency_field="currency_id", default=0.0)
    useful_life_months = fields.Integer(required=True)
    start_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    declining_factor = fields.Float(
        default=2.0,
        help="Multiplier for declining balance (2.0 = double-declining).",
    )
    line_ids = fields.One2many("fms.asset.depreciation.line", "schedule_id", string="Lines")
    accumulated_depreciation = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    book_value = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    pending_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")

    _sql_constraints = [
        (
            "fms_depreciation_useful_life_positive",
            "CHECK(useful_life_months > 0)",
            "Useful life must be greater than zero months.",
        ),
    ]

    @api.depends("line_ids", "line_ids.state", "line_ids.depreciation_amount", "acquisition_cost", "residual_value")
    def _compute_totals(self):
        for record in self:
            posted = record.line_ids.filtered(lambda line: line.state == "posted")
            pending = record.line_ids.filtered(lambda line: line.state == "pending")
            accumulated = sum(posted.mapped("depreciation_amount"))
            record.accumulated_depreciation = accumulated
            record.book_value = max(record.acquisition_cost - accumulated, record.residual_value)
            record.pending_amount = sum(pending.mapped("depreciation_amount"))

    @api.constrains("equipment_id", "state")
    def _check_single_running_schedule(self):
        for record in self.filtered(lambda r: r.state in ("draft", "running")):
            others = self.search(
                [
                    ("id", "!=", record.id),
                    ("equipment_id", "=", record.equipment_id.id),
                    ("state", "in", ("draft", "running")),
                ]
            )
            if others:
                raise ValidationError(
                    _("Asset %s already has an active depreciation schedule.", record.equipment_id.display_name)
                )

    def _round_amount(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        return float_round(amount, precision_rounding=currency.rounding)

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_generate_lines(self):
        for record in self:
            if record.equipment_id.fms_operations_locked:
                raise ValidationError(_("Cannot generate depreciation for a disposed asset."))
            if record.method in ("manual", "units"):
                raise ValidationError(
                    _("Automatic line generation is not available for method %s.", dict(DEPRECIATION_METHODS).get(record.method))
                )
            record.line_ids.unlink()
            record._generate_depreciation_lines()
            record.write({"state": "running"})
            record.equipment_id._fms_log_lifecycle_event(
                "financial",
                _("Depreciation schedule activated (%s).", dict(DEPRECIATION_METHODS).get(record.method)),
            )
        return True

    def _generate_depreciation_lines(self):
        self.ensure_one()
        Line = self.env["fms.asset.depreciation.line"]
        depreciable = self.acquisition_cost - self.residual_value
        if depreciable <= 0:
            return

        book = self.acquisition_cost
        lines = []
        period_date = self.start_date
        for period in range(1, self.useful_life_months + 1):
            if book <= self.residual_value:
                break
            amount = self._compute_period_amount(book, period, depreciable)
            amount = min(amount, book - self.residual_value)
            amount = self._round_amount(amount)
            if amount <= 0:
                break
            lines.append(
                {
                    "schedule_id": self.id,
                    "period_number": period,
                    "period_date": period_date,
                    "depreciation_amount": amount,
                    "state": "pending",
                }
            )
            book -= amount
            period_date = fields.Date.to_date(period_date) + relativedelta(months=1)

        for vals in lines:
            Line.create(vals)

    def _compute_period_amount(self, current_book, period_number, depreciable_base):
        self.ensure_one()
        if self.method == "straight_line":
            return depreciable_base / self.useful_life_months
        if self.method == "declining":
            rate = self.declining_factor / self.useful_life_months
            return current_book * rate
        return 0.0

    def action_post_due_lines(self, as_of_date=None):
        as_of_date = as_of_date or fields.Date.context_today(self)
        for record in self.filtered(lambda r: r.state == "running"):
            due_lines = record.line_ids.filtered(
                lambda line: line.state == "pending" and line.period_date <= as_of_date
            )
            for line in due_lines:
                line.action_post()
            if record.line_ids and not record.line_ids.filtered(lambda line: line.state == "pending"):
                record.write({"state": "completed"})
        return True

    @api.model
    def cron_post_due_depreciation_lines(self):
        running = self.search([("state", "=", "running")])
        running.action_post_due_lines()
        return True

    @api.model
    def fms_create_schedule(self, equipment_id, payload=None):
        if not self.has_access("create"):
            raise ValidationError(_("You are not allowed to create depreciation schedules."))
        payload = payload or {}
        equipment = self.env["maintenance.equipment"].browse(int(equipment_id))
        equipment.check_access("read")
        if equipment.fms_operations_locked:
            raise ValidationError(_("Cannot depreciate a disposed asset."))
        acquisition_cost = float(payload.get("acquisition_cost") or equipment.cost or 0.0)
        if acquisition_cost <= 0:
            raise ValidationError(_("Acquisition cost must be greater than zero to create a schedule."))
        method = payload.get("method") or equipment.fms_depreciation_method or equipment.fms_classification_id.default_depreciation_method or "straight_line"
        useful_life = int(
            payload.get("useful_life_months")
            or equipment.fms_useful_life_months
            or equipment.fms_classification_id.default_useful_life_months
            or 60
        )
        residual = float(payload.get("residual_value") if payload.get("residual_value") is not None else equipment.fms_residual_value or 0.0)
        start_date = payload.get("start_date") or equipment.fms_acquisition_date or fields.Date.context_today(self)
        schedule = self.create(
            {
                "name": payload.get("name") or _("Depreciation — %s", equipment.fms_asset_code or equipment.name),
                "equipment_id": equipment.id,
                "method": method,
                "acquisition_cost": acquisition_cost,
                "residual_value": residual,
                "useful_life_months": useful_life,
                "start_date": start_date,
                "declining_factor": float(payload.get("declining_factor") or 2.0),
            }
        )
        if payload.get("auto_generate"):
            schedule.action_generate_lines()
        return {"id": schedule.id, "state": schedule.state, "line_count": len(schedule.line_ids)}

    def fms_get_schedule_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "state": self.state,
            "method": self.method,
            "acquisition_cost": self.acquisition_cost,
            "residual_value": self.residual_value,
            "useful_life_months": self.useful_life_months,
            "start_date": fields.Date.to_string(self.start_date),
            "accumulated_depreciation": self.accumulated_depreciation,
            "book_value": self.book_value,
            "pending_amount": self.pending_amount,
            "lines": [
                {
                    "id": line.id,
                    "period_number": line.period_number,
                    "period_date": fields.Date.to_string(line.period_date),
                    "depreciation_amount": line.depreciation_amount,
                    "state": line.state,
                    "journal_entry_ref": line.journal_entry_ref,
                }
                for line in self.line_ids[:120]
            ],
        }


class FmsAssetDepreciationLine(models.Model):
    _name = "fms.asset.depreciation.line"
    _description = "FMS Asset Depreciation Line"
    _order = "period_number, id"

    schedule_id = fields.Many2one(
        "fms.asset.depreciation.schedule",
        required=True,
        ondelete="cascade",
        index=True,
    )
    equipment_id = fields.Many2one(related="schedule_id.equipment_id", store=True, index=True)
    company_id = fields.Many2one(related="schedule_id.company_id", store=True)
    currency_id = fields.Many2one(related="schedule_id.currency_id")
    period_number = fields.Integer(required=True)
    period_date = fields.Date(required=True, index=True)
    depreciation_amount = fields.Monetary(currency_field="currency_id", required=True)
    state = fields.Selection(LINE_STATES, default="pending", required=True, index=True)
    posted_date = fields.Date()
    journal_entry_ref = fields.Char(
        string="Journal Entry Ref",
        help="Reference to Odoo account.move name when accounting bridge posts GL entries.",
    )

    def action_post(self):
        for line in self:
            if line.state != "pending":
                continue
            if line.schedule_id.state not in ("running", "draft"):
                raise ValidationError(_("Cannot post lines on a %s schedule.", line.schedule_id.state))
            line.write({"state": "posted", "posted_date": fields.Date.context_today(line)})
            line._fms_try_post_accounting_entry()
            line.equipment_id._fms_log_lifecycle_event(
                "financial",
                _("Depreciation posted: %(amount)s (period %(period)s).", amount=line.depreciation_amount, period=line.period_number),
            )
        return True

    def action_skip(self):
        self.filtered(lambda line: line.state == "pending").write({"state": "skipped"})
        return True

    def _fms_try_post_accounting_entry(self):
        self.ensure_one()
        Move = self.env.get("account.move")
        if not Move:
            return False
        config = self.env["fms.asset.accounting.config"].sudo().search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not config or not config.auto_post_journal:
            return False
        if not config.depreciation_expense_account_code or not config.accumulated_depreciation_account_code:
            return False

        Account = self.env["account.account"]
        Journal = self.env["account.journal"]
        expense_account = Account.search(
            [("code", "=", config.depreciation_expense_account_code), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        accum_account = Account.search(
            [("code", "=", config.accumulated_depreciation_account_code), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        journal = Journal.search([("code", "=", config.journal_code), ("company_id", "=", self.company_id.id)], limit=1)
        if not expense_account or not accum_account or not journal:
            return False

        asset_label = self.equipment_id.fms_asset_code or self.equipment_id.name
        move = Move.create(
            {
                "move_type": "entry",
                "date": self.period_date,
                "journal_id": journal.id,
                "ref": _("FMS depreciation %(asset)s P%(period)s", asset=asset_label, period=self.period_number),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": _("Depreciation expense"),
                            "account_id": expense_account.id,
                            "debit": self.depreciation_amount,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": _("Accumulated depreciation"),
                            "account_id": accum_account.id,
                            "debit": 0.0,
                            "credit": self.depreciation_amount,
                        },
                    ),
                ],
            }
        )
        if hasattr(move, "action_post"):
            move.action_post()
        self.write({"journal_entry_ref": move.name})
        return True