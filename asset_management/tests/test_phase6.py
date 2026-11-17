# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetPhase6(TransactionCase):
    def test_dashboard_ui_payload_fields(self):
        data = self.env["fms.asset.dashboard"].get_dashboard_data()
        self.assertIn("recent_assets", data)
        self.assertIsInstance(data["recent_assets"], list)