# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetPhase3(TransactionCase):
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
            {"name": "LV Panel", "code": "LVP", "level": "subtype", "parent_id": asset_type.id}
        )

    def test_registration_wizard_creates_asset(self):
        created = self.env["fms.asset.registration.wizard"].fms_register_asset(
            {
                "name": "Panel Board 1",
                "fms_classification_id": self.subtype.id,
                "fms_confirm_active": True,
            }
        )
        equipment = self.env["maintenance.equipment"].browse(created["id"])
        self.assertEqual(equipment.fms_lifecycle_state, "active")
        self.assertTrue(equipment.fms_lifecycle_event_ids)

    def test_assignment_and_histories_are_separate(self):
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Assignable Asset",
                "fms_classification_id": self.subtype.id,
                "fms_lifecycle_state": "active",
            }
        )
        self.env["fms.asset.assignment"].fms_create_assignment(
            equipment.id,
            {
                "assignment_type": "department",
                "department": "MEP",
            },
        )
        self.assertTrue(equipment.fms_assignment_history_ids)
        self.assertTrue(equipment.fms_lifecycle_event_ids.filtered(lambda e: e.event_type == "assignment"))

    def test_detail_payload(self):
        equipment = self.env["maintenance.equipment"].create(
            {"name": "Detail Asset", "fms_classification_id": self.subtype.id}
        )
        payload = equipment.fms_get_detail_payload_by_id(equipment.id)
        self.assertEqual(payload["id"], equipment.id)
        self.assertIn("lifecycle_events", payload)