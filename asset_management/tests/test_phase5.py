# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetPhase5(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env["fms.asset.classification"].create(
            {"name": "Electrical", "code": "EL", "level": "category"}
        )
        asset_type = cls.env["fms.asset.classification"].create(
            {"name": "Panel", "code": "PNL", "level": "type", "parent_id": category.id}
        )
        cls.subtype = cls.env["fms.asset.classification"].create(
            {
                "name": "LV Panel",
                "code": "LVP",
                "level": "subtype",
                "parent_id": asset_type.id,
                "default_useful_life_months": 12,
                "default_depreciation_method": "straight_line",
            }
        )

    def test_straight_line_schedule_and_post(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Depreciable Asset",
                "fms_classification_id": self.subtype.id,
                "fms_lifecycle_state": "active",
                "cost": 12000.0,
                "fms_residual_value": 0.0,
                "fms_useful_life_months": 12,
                "fms_depreciation_method": "straight_line",
                "fms_acquisition_date": fields.Date.today(),
            }
        )
        created = self.env["fms.asset.depreciation.schedule"].fms_create_schedule(
            equipment.id, {"auto_generate": True}
        )
        schedule = self.env["fms.asset.depreciation.schedule"].browse(created["id"])
        self.assertEqual(schedule.state, "running")
        self.assertEqual(len(schedule.line_ids), 12)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped("depreciation_amount")), 12000.0, places=2)
        schedule.action_post_due_lines()
        equipment.invalidate_recordset()
        self.assertGreater(equipment.fms_accumulated_depreciation, 0.0)
        self.assertLess(equipment.fms_book_value, equipment.cost)

    def test_disposal_uses_book_value(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Dispose Book",
                "fms_classification_id": self.subtype.id,
                "cost": 6000.0,
                "fms_useful_life_months": 6,
                "fms_depreciation_method": "straight_line",
            }
        )
        created = self.env["fms.asset.depreciation.schedule"].fms_create_schedule(
            equipment.id, {"auto_generate": True}
        )
        schedule = self.env["fms.asset.depreciation.schedule"].browse(created["id"])
        schedule.line_ids[:2].action_post()
        equipment.invalidate_recordset()
        disposal_data = self.env["fms.asset.disposal"].fms_create_disposal(
            equipment.id, {"disposal_reason": "obsolete", "submit": False}
        )
        disposal = self.env["fms.asset.disposal"].browse(disposal_data["id"])
        self.assertAlmostEqual(disposal.book_value, equipment.fms_book_value, places=2)

    def test_manual_method_blocks_auto_generation(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Manual Asset",
                "fms_classification_id": self.subtype.id,
                "cost": 1000.0,
                "fms_depreciation_method": "manual",
            }
        )
        created = self.env["fms.asset.depreciation.schedule"].fms_create_schedule(equipment.id, {})
        schedule = self.env["fms.asset.depreciation.schedule"].browse(created["id"])
        with self.assertRaises(ValidationError):
            schedule.action_generate_lines()

    def test_dashboard_depreciation_metrics(self):
        data = self.env["fms.asset.dashboard"].get_dashboard_data()
        self.assertIn("depreciation_due_count", data)
        self.assertIn("assets_without_depreciation_schedule", data)
        self.assertIn("total_book_value", data)