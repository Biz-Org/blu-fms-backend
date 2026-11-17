# -*- coding: utf-8 -*-

from odoo.modules.module import get_manifest
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetInstall(TransactionCase):
    def test_module_installed(self):
        module = self.env["ir.module.module"].search([("name", "=", "fms_asset_management")], limit=1)
        self.assertEqual(module.state, "installed")

    def test_manifest_dependencies(self):
        manifest = get_manifest("fms_asset_management")
        self.assertEqual(manifest.get("depends"), ["maintenance", "mail"])
        self.assertTrue(manifest.get("application"))
        self.assertTrue(manifest["version"].startswith("18.0"))
        self.assertGreaterEqual(manifest["version"], "18.0.6.0.0")

    def test_release_validation_green(self):
        report = self.env["fms.asset.validation"].run_release_checks()
        self.assertTrue(report["ok"], report)

    def test_crons_registered(self):
        for model in ("fms.asset.warranty", "fms.asset.depreciation.schedule"):
            cron = self.env["ir.cron"].sudo().search([("model_id.model", "=", model)], limit=1)
            self.assertTrue(cron, model)

    def test_asset_label_report_registered(self):
        self.env.ref("fms_asset_management.action_report_fms_asset_label")

    def test_phase3_models_registered(self):
        for model in (
            "fms.asset.assignment",
            "fms.asset.assignment.history",
            "fms.asset.lifecycle.event",
            "fms.asset.registration.wizard",
        ):
            self.assertIn(model, self.env)

    def test_phase4_models_registered(self):
        for model in (
            "fms.asset.warranty",
            "fms.asset.amc",
            "fms.asset.inspection",
            "fms.asset.transfer",
            "fms.asset.disposal",
        ):
            self.assertIn(model, self.env)

    def test_phase5_models_registered(self):
        for model in (
            "fms.asset.depreciation.schedule",
            "fms.asset.depreciation.line",
            "fms.asset.accounting.config",
        ):
            self.assertIn(model, self.env)

    def test_security_groups_exist(self):
        for xmlid in (
            "group_asset_administrator",
            "group_asset_manager",
            "group_asset_facility_manager",
            "group_asset_technician",
            "group_asset_finance",
            "group_asset_auditor",
        ):
            self.env.ref(f"fms_asset_management.{xmlid}")

    def test_models_registered(self):
        for model in (
            "fms.asset.classification",
            "fms.asset.location",
            "fms.asset.dashboard",
        ):
            self.assertIn(model, self.env)

    def test_sequence_exists(self):
        seq = self.env.ref("fms_asset_management.seq_fms_asset_code")
        self.assertEqual(seq.code, "fms.asset.code")

    def test_root_menu_opens_owl_dashboard(self):
        menu = self.env.ref("fms_asset_management.menu_fms_asset_root")
        action = self.env["ir.actions.client"].browse(menu.action.id)
        self.assertEqual(action.tag, "fms_asset_management.action_dashboard")

    def test_client_actions_registered(self):
        mapping = {
            "action_am_dashboard_ui": "fms_asset_management.action_dashboard",
            "action_am_register_ui": "fms_asset_management.action_register",
            "action_am_registration_ui": "fms_asset_management.action_registration",
            "action_am_detail_ui": "fms_asset_management.action_detail",
            "action_am_operations_ui": "fms_asset_management.action_operations",
            "action_am_qr_ui": "fms_asset_management.action_qr",
        }
        for xmlid, tag in mapping.items():
            action = self.env.ref(f"fms_asset_management.{xmlid}")
            self.assertEqual(action.type, "ir.actions.client")
            self.assertEqual(action.tag, tag)
