# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestFmsAssetPhase7(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env["fms.asset.classification"].create(
            {"name": "MEP", "code": "MEP", "level": "category"}
        )
        asset_type = cls.env["fms.asset.classification"].create(
            {"name": "Pump", "code": "PMP", "level": "type", "parent_id": category.id}
        )
        cls.subtype = cls.env["fms.asset.classification"].create(
            {
                "name": "Booster Pump",
                "code": "BSP",
                "level": "subtype",
                "parent_id": asset_type.id,
                "default_useful_life_months": 6,
            }
        )
        cls.property_loc = cls.env["fms.asset.location"].create(
            {"name": "Site A", "code": "SA", "location_type": "property"}
        )
        cls.building = cls.env["fms.asset.location"].create(
            {"name": "Block 1", "code": "B1", "location_type": "building", "parent_id": cls.property_loc.id}
        )
        cls.floor = cls.env["fms.asset.location"].create(
            {"name": "L1", "code": "L1", "location_type": "floor", "parent_id": cls.building.id}
        )
        cls.wing = cls.env["fms.asset.location"].create(
            {"name": "West", "code": "W", "location_type": "wing_area", "parent_id": cls.floor.id}
        )
        cls.room_a = cls.env["fms.asset.location"].create(
            {"name": "Pump Room", "code": "PR", "location_type": "room", "parent_id": cls.wing.id}
        )
        cls.room_b = cls.env["fms.asset.location"].create(
            {"name": "Store", "code": "ST", "location_type": "room", "parent_id": cls.wing.id}
        )

    def test_release_validation_passes_on_installed_module(self):
        report = self.env["fms.asset.validation"].run_release_checks()
        self.assertTrue(report["ok"], report)
        for row in report["checks"]:
            self.assertTrue(row["ok"], row)

    def test_full_lifecycle_maintenance_integration(self):
        created = self.env["fms.asset.registration.wizard"].fms_register_asset(
            {
                "name": "Integration Pump",
                "fms_classification_id": self.subtype.id,
                "fms_location_id": self.room_a.id,
                "cost": 6000.0,
                "fms_useful_life_months": 6,
                "fms_depreciation_method": "straight_line",
                "fms_confirm_active": True,
            }
        )
        equipment = self.env["maintenance.equipment"].browse(created["id"])
        self.assertEqual(equipment.fms_lifecycle_state, "active")
        self.assertTrue(equipment.fms_qr_token)

        self.env["fms.asset.assignment"].fms_create_assignment(
            equipment.id, {"assignment_type": "department", "department": "MEP"}
        )
        self.env["fms.asset.inspection"].fms_create_inspection(
            equipment.id, {"name": "Startup", "condition": "good", "health_status": "healthy", "complete": True}
        )
        transfer_data = self.env["fms.asset.transfer"].fms_create_transfer(
            equipment.id, {"to_location_id": self.room_b.id, "reason": "Relocation", "submit": True}
        )
        transfer = self.env["fms.asset.transfer"].browse(transfer_data["id"])
        transfer.action_approve()
        transfer.action_complete()
        equipment.invalidate_recordset()
        self.assertEqual(equipment.fms_location_id.id, self.room_b.id)

        self.env["fms.asset.depreciation.schedule"].fms_create_schedule(
            equipment.id, {"auto_generate": True}
        )
        equipment.invalidate_recordset()
        self.assertGreater(equipment.fms_book_value, 0.0)

        request = self.env["maintenance.request"].create(
            {"name": "Pump noise", "equipment_id": equipment.id, "maintenance_type": "corrective"}
        )
        self.assertEqual(request.equipment_id.id, equipment.id)

        disposal_data = self.env["fms.asset.disposal"].fms_create_disposal(
            equipment.id, {"disposal_reason": "end_of_life", "submit": True}
        )
        disposal = self.env["fms.asset.disposal"].browse(disposal_data["id"])
        disposal.action_approve()
        disposal.action_dispose()
        equipment.invalidate_recordset()
        self.assertEqual(equipment.fms_lifecycle_state, "disposed")

    def test_cron_jobs_run_without_error(self):
        self.env["fms.asset.warranty"].cron_refresh_fms_contract_status()
        self.env["fms.asset.depreciation.schedule"].cron_post_due_depreciation_lines()

    def test_finance_user_can_create_depreciation_schedule(self):
        finance_user = new_test_user(
            self.env,
            login="asset_finance_phase7",
            groups="fms_asset_management.group_asset_finance",
        )
        equipment = self.env["maintenance.equipment"].create(
            {
                "name": "Finance Asset",
                "fms_classification_id": self.subtype.id,
                "cost": 1200.0,
                "fms_depreciation_method": "straight_line",
                "fms_useful_life_months": 12,
            }
        )
        created = (
            self.env["fms.asset.depreciation.schedule"]
            .with_user(finance_user)
            .fms_create_schedule(equipment.id, {"auto_generate": True})
        )
        self.assertTrue(created.get("id"))

    def test_technician_cannot_approve_transfer(self):
        technician = new_test_user(
            self.env,
            login="asset_tech_phase7",
            groups="fms_asset_management.group_asset_technician",
        )
        equipment = self.env["maintenance.equipment"].create(
            {"name": "Tech Asset", "fms_classification_id": self.subtype.id, "fms_lifecycle_state": "active"}
        )
        transfer_data = self.env["fms.asset.transfer"].fms_create_transfer(
            equipment.id, {"to_location_id": self.room_b.id, "submit": True}
        )
        transfer = self.env["fms.asset.transfer"].browse(transfer_data["id"])
        with self.assertRaises(AccessError):
            transfer.with_user(technician).action_approve()

    def test_equipment_company_rule_hides_other_company(self):
        company_b = self.env["res.company"].create({"name": "FMS Asset Co B"})
        user_b = new_test_user(
            self.env,
            login="asset_manager_co_b",
            groups="fms_asset_management.group_asset_manager",
            company_id=company_b.id,
            company_ids=[company_b.id],
        )
        secret = self.env["maintenance.equipment"].with_user(user_b).create(
            {
                "name": "Hidden Co B Asset",
                "company_id": company_b.id,
                "fms_lifecycle_state": "draft",
            }
        )
        user_a = new_test_user(
            self.env,
            login="asset_manager_co_a",
            groups="fms_asset_management.group_asset_manager",
            company_id=self.env.company.id,
            company_ids=[self.env.company.id],
        )
        visible_a = self.env["maintenance.equipment"].with_user(user_a).search([("id", "=", secret.id)])
        self.assertFalse(visible_a)
        visible_b = self.env["maintenance.equipment"].with_user(user_b).search([("id", "=", secret.id)])
        self.assertEqual(visible_b.id, secret.id)