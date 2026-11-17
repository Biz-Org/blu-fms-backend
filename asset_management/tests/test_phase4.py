# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFmsAssetPhase4(TransactionCase):
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
        cls.property_loc = cls.env["fms.asset.location"].create(
            {"name": "HQ Site", "code": "HQ", "location_type": "property"}
        )
        cls.building = cls.env["fms.asset.location"].create(
            {"name": "Tower A", "code": "T-A", "location_type": "building", "parent_id": cls.property_loc.id}
        )
        cls.floor = cls.env["fms.asset.location"].create(
            {"name": "Floor 3", "code": "F3", "location_type": "floor", "parent_id": cls.building.id}
        )
        cls.wing = cls.env["fms.asset.location"].create(
            {"name": "East Wing", "code": "EW", "location_type": "wing_area", "parent_id": cls.floor.id}
        )
        cls.room_a = cls.env["fms.asset.location"].create(
            {"name": "Plant Room 3B", "code": "PR3B", "location_type": "room", "parent_id": cls.wing.id}
        )
        cls.room_b = cls.env["fms.asset.location"].create(
            {"name": "Plant Room 3C", "code": "PR3C", "location_type": "room", "parent_id": cls.wing.id}
        )

    def _active_equipment(self, **extra):
        values = {
            "name": "Phase4 Asset",
            "fms_classification_id": self.subtype.id,
            "fms_lifecycle_state": "active",
            "fms_location_id": self.room_a.id,
        }
        values.update(extra)
        return self.env["maintenance.equipment"].create(values)

    def test_qr_token_on_create_and_resolve(self):
        equipment = self._active_equipment()
        self.assertTrue(equipment.fms_qr_token)
        resolved = self.env["maintenance.equipment"].fms_resolve_qr_token(equipment.fms_qr_token)
        self.assertEqual(resolved["id"], equipment.id)

    def test_transfer_workflow_updates_location(self):
        equipment = self._active_equipment()
        created = self.env["fms.asset.transfer"].fms_create_transfer(
            equipment.id,
            {"to_location_id": self.room_b.id, "reason": "Relocation", "submit": True},
        )
        transfer = self.env["fms.asset.transfer"].browse(created["id"])
        self.assertEqual(transfer.state, "submitted")
        transfer.action_approve()
        transfer.action_complete()
        equipment.invalidate_recordset()
        self.assertEqual(equipment.fms_location_id.id, self.room_b.id)

    def test_disposal_workflow_locks_asset(self):
        equipment = self._active_equipment()
        self.env["fms.asset.assignment"].fms_create_assignment(
            equipment.id, {"assignment_type": "department", "department": "OPS"}
        )
        created = self.env["fms.asset.disposal"].fms_create_disposal(
            equipment.id, {"disposal_reason": "end_of_life", "remarks": "Retired", "submit": True}
        )
        disposal = self.env["fms.asset.disposal"].browse(created["id"])
        disposal.action_approve()
        disposal.action_dispose()
        equipment.invalidate_recordset()
        self.assertEqual(equipment.fms_lifecycle_state, "disposed")
        self.assertTrue(equipment.fms_operations_locked)
        self.assertFalse(equipment.fms_current_assignment_id)

    def test_inspection_updates_health(self):
        equipment = self._active_equipment()
        self.env["fms.asset.inspection"].fms_create_inspection(
            equipment.id,
            {
                "name": "Quarterly check",
                "condition": "fair",
                "health_status": "attention",
                "complete": True,
            },
        )
        equipment.invalidate_recordset()
        self.assertEqual(equipment.fms_condition, "fair")
        self.assertEqual(equipment.fms_health_status, "attention")

    def test_maintenance_request_blocked_when_disposed(self):
        equipment = self._active_equipment()
        equipment.action_fms_set_disposed()
        with self.assertRaises(ValidationError):
            self.env["maintenance.request"].create(
                {"name": "Should fail", "equipment_id": equipment.id, "maintenance_type": "corrective"}
            )

    def test_detail_payload_includes_phase4_collections(self):
        equipment = self._active_equipment()
        payload = equipment.fms_get_detail_payload_by_id(equipment.id)
        for key in ("warranties", "amc_contracts", "inspections", "transfers", "disposals", "fms_qr_token"):
            self.assertIn(key, payload)