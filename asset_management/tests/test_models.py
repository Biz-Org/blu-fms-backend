# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env["fms.asset.classification"].create(
            {"name": "HVAC", "code": "HVAC", "level": "category"}
        )
        cls.asset_type = cls.env["fms.asset.classification"].create(
            {"name": "Chiller", "code": "CH", "level": "type", "parent_id": cls.category.id}
        )
        cls.subtype = cls.env["fms.asset.classification"].create(
            {
                "name": "Centrifugal",
                "code": "CH-CF",
                "level": "subtype",
                "parent_id": cls.asset_type.id,
                "default_useful_life_months": 120,
            }
        )
        cls.property_loc = cls.env["fms.asset.location"].create(
            {"name": "HQ Site", "code": "HQ", "location_type": "property"}
        )
        cls.building = cls.env["fms.asset.location"].create(
            {
                "name": "Tower A",
                "code": "T-A",
                "location_type": "building",
                "parent_id": cls.property_loc.id,
            }
        )
        cls.floor = cls.env["fms.asset.location"].create(
            {"name": "Floor 3", "code": "F3", "location_type": "floor", "parent_id": cls.building.id}
        )
        cls.wing = cls.env["fms.asset.location"].create(
            {"name": "East Wing", "code": "EW", "location_type": "wing_area", "parent_id": cls.floor.id}
        )
        cls.room = cls.env["fms.asset.location"].create(
            {"name": "Plant Room 3B", "code": "PR3B", "location_type": "room", "parent_id": cls.wing.id}
        )

    def test_equipment_create_assigns_asset_code_and_serial(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Chiller Unit 1",
                "fms_classification_id": self.subtype.id,
                "fms_location_id": self.room.id,
                "fms_lifecycle_state": "active",
            }
        )
        self.assertTrue(equipment.fms_asset_code)
        self.assertEqual(equipment.serial_no, equipment.fms_asset_code)
        self.assertEqual(equipment.location, self.room.complete_name)

    def test_disposal_does_not_archive(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Desk Asset",
                "fms_classification_id": self.subtype.id,
                "fms_lifecycle_state": "active",
            }
        )
        equipment.action_fms_set_disposed()
        self.assertEqual(equipment.fms_lifecycle_state, "disposed")
        self.assertTrue(equipment.active)
        self.assertTrue(equipment.fms_operations_locked)

    def test_disposed_blocks_location_change(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Disposed Pump",
                "fms_classification_id": self.subtype.id,
                "fms_location_id": self.room.id,
                "fms_lifecycle_state": "active",
            }
        )
        equipment.action_fms_set_disposed()
        with self.assertRaises(ValidationError):
            equipment.write({"fms_location_id": self.env["fms.asset.location"].create(
                {
                    "name": "Other Room",
                    "code": "OR",
                    "location_type": "room",
                    "parent_id": self.wing.id,
                }
            ).id})

    def test_dashboard_returns_live_counts(self):
        before = self.env["fms.asset.dashboard"].get_dashboard_data()
        self.env["maintenance.equipment"].create(
            {
                "name": "IT Laptop",
                "fms_classification_id": self.subtype.id,
                "fms_lifecycle_state": "active",
            }
        )
        after = self.env["fms.asset.dashboard"].get_dashboard_data()
        self.assertGreaterEqual(after["total_assets"], before["total_assets"] + 1)

    def test_classification_must_be_subtype(self):
        with self.assertRaises(ValidationError):
            self.env["maintenance.equipment"].create(
                {
                    "name": "Bad Class",
                    "fms_classification_id": self.category.id,
                }
            )
