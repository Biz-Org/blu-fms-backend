# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = new_test_user(
            cls.env,
            login="asset_auditor_test",
            groups="fms_asset_management.group_asset_auditor",
        )
        cls.finance = new_test_user(
            cls.env,
            login="asset_finance_test",
            groups="fms_asset_management.group_asset_finance",
        )
        category = cls.env["fms.asset.classification"].create(
            {"name": "Furniture", "code": "FRN", "level": "category"}
        )
        asset_type = cls.env["fms.asset.classification"].create(
            {"name": "Chair", "code": "CHR", "level": "type", "parent_id": category.id}
        )
        cls.leaf = cls.env["fms.asset.classification"].create(
            {"name": "Ergonomic", "code": "ERG", "level": "subtype", "parent_id": asset_type.id}
        )

    def test_auditor_cannot_create_equipment(self):
        with self.assertRaises(AccessError):
            self.env["maintenance.equipment"].with_user(self.auditor).create(
                {"name": "Chair 1", "fms_classification_id": self.leaf.id}
            )

    def test_finance_cannot_create_equipment(self):
        with self.assertRaises(AccessError):
            self.env["maintenance.equipment"].with_user(self.finance).create(
                {"name": "Chair 2", "fms_classification_id": self.leaf.id}
            )

    def test_finance_can_read_dashboard(self):
        data = self.env["fms.asset.dashboard"].with_user(self.finance).get_dashboard_data()
        self.assertIn("available", data)