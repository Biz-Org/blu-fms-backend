# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.modules.module import get_manifest
from odoo.tools.translate import _


class FmsAssetValidation(models.AbstractModel):
    _name = "fms.asset.validation"
    _description = "FMS Asset Release / Integration Validation"

    @api.model
    def run_release_checks(self):
        """Automated install/integration checks for release hardening (Phase 7)."""
        checks = []
        checks.append(self._check_module_manifest())
        checks.append(self._check_sequences())
        checks.append(self._check_cron_jobs())
        checks.append(self._check_client_actions())
        checks.append(self._check_maintenance_bridge())
        checks.append(self._check_optional_accounting_bridge())
        ok = all(row["ok"] for row in checks)
        manifest = get_manifest("fms_asset_management") or {}
        return {
            "ok": ok,
            "module_version": manifest.get("version"),
            "checks": checks,
        }

    def _append(self, name, ok, details=""):
        return {"name": name, "ok": bool(ok), "details": details or ""}

    def _check_module_manifest(self):
        manifest = get_manifest("fms_asset_management") or {}
        deps = manifest.get("depends") or []
        ok = manifest.get("installable") and "maintenance" in deps and "mail" in deps
        return self._append(
            "module_manifest",
            ok,
            _("depends=%s version=%s") % (",".join(deps), manifest.get("version")),
        )

    def _check_sequences(self):
        codes = ("fms.asset.code", "fms.asset.transfer", "fms.asset.disposal")
        seq = self.env["ir.sequence"].sudo()
        missing = [code for code in codes if not seq.search([("code", "=", code)], limit=1)]
        return self._append("sequences", not missing, _("missing: %s") % ", ".join(missing) if missing else "ok")

    def _check_cron_jobs(self):
        crons = self.env["ir.cron"].sudo().search(
            [("model_id.model", "in", ("fms.asset.warranty", "fms.asset.depreciation.schedule"))]
        )
        ok = len(crons) >= 2
        return self._append(
            "scheduled_actions",
            ok,
            _("found %s FMS asset crons") % len(crons),
        )

    def _check_client_actions(self):
        tags = (
            "fms_asset_management.action_dashboard",
            "fms_asset_management.action_register",
            "fms_asset_management.action_registration",
            "fms_asset_management.action_detail",
            "fms_asset_management.action_operations",
            "fms_asset_management.action_qr",
        )
        Client = self.env["ir.actions.client"].sudo()
        missing = [tag for tag in tags if not Client.search([("tag", "=", tag)], limit=1)]
        return self._append("owl_client_actions", not missing, _("missing: %s") % ", ".join(missing) if missing else "ok")

    def _check_maintenance_bridge(self):
        equipment = self.env["maintenance.equipment"]
        field_names = {
            "fms_asset_code",
            "fms_lifecycle_state",
            "fms_classification_id",
            "fms_location_id",
            "fms_book_value",
        }
        missing = sorted(field_names - set(equipment._fields.keys()))
        request_guard = "maintenance.request" in self.env and hasattr(
            self.env["maintenance.request"], "create"
        )
        ok = not missing and request_guard
        details = []
        if missing:
            details.append(_("equipment fields missing: %s") % ", ".join(missing))
        if not request_guard:
            details.append(_("maintenance.request bridge missing"))
        return self._append("maintenance_bridge", ok, "; ".join(details) or "ok")

    def _check_optional_accounting_bridge(self):
        installed = bool(
            self.env["ir.module.module"].sudo().search(
                [("name", "=", "account"), ("state", "=", "installed")], limit=1
            )
        )
        config_model = "fms.asset.accounting.config" in self.env
        if not config_model:
            return self._append("accounting_bridge", False, _("accounting config model missing"))
        message = _("accounting app installed=%s; bridge config model available") % installed
        return self._append("accounting_bridge", True, message)