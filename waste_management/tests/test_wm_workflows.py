# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'waste_management')
class TestWmWorkflows(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['wm.dashboard']
        cls.partner = cls.env['res.partner'].create({
            'name': 'WM Test Vendor Partner',
            'supplier_rank': 1,
        })
        cls.vendor = cls.env['wm.vendor'].create({
            'partner_id': cls.partner.id,
            'waste_categories': 'Plastic, Paper',
            'recycling_capability': True,
            'disposal_capability': True,
            'state': 'active',
        })

    def _make_entry(self, **kwargs):
        vals = {
            'waste_type': 'Paper',
            'waste_category': 'dry',
            'quantity': 100.0,
            'site': 'Site Alpha',
            'location_detail': 'Loading Dock',
        }
        vals.update(kwargs)
        return self.env['wm.entry'].create(vals)

    def test_entry_create_and_confirm(self):
        entry = self._make_entry()
        self.assertTrue(entry.code.startswith('WM-ENTRY-'))
        self.assertEqual(entry.state, 'draft')
        entry.action_confirm()
        self.assertEqual(entry.state, 'pending_segregation')

    def test_entry_quantity_validation(self):
        with self.assertRaises(ValidationError):
            self._make_entry(quantity=0)

    def test_entry_invalid_cancel_from_processed(self):
        entry = self._make_entry()
        entry.action_confirm()
        entry.action_mark_processed()
        with self.assertRaises(UserError):
            entry.action_cancel()

    def test_segregation_quantity_and_workflow(self):
        entry = self._make_entry(quantity=50)
        entry.action_confirm()
        seg = self.env['wm.segregation'].create({
            'entry_id': entry.id,
            'original_qty': 50,
            'dry_qty': 20,
            'wet_qty': 10,
        })
        seg.action_start()
        self.assertEqual(seg.state, 'in_progress')
        seg.action_complete()
        self.assertEqual(seg.state, 'completed')
        self.assertEqual(entry.state, 'processed')

    def test_segregation_qty_exceeds_original(self):
        entry = self._make_entry(quantity=10)
        with self.assertRaises(ValidationError):
            self.env['wm.segregation'].create({
                'entry_id': entry.id,
                'original_qty': 10,
                'dry_qty': 8,
                'wet_qty': 5,
            })

    def test_collection_and_pickup(self):
        entry = self._make_entry(quantity=80)
        entry.action_confirm()
        schedule = self.env['wm.collection.schedule'].create({
            'entry_id': entry.id,
            'quantity': 80,
            'pickup_date': fields.Date.today(),
            'site': 'Site Alpha',
            'vendor_id': self.vendor.id,
        })
        schedule.action_schedule()
        self.assertEqual(schedule.state, 'scheduled')
        self.assertTrue(schedule.pickup_ids)
        schedule.action_confirm()
        schedule.action_start()
        self.assertEqual(schedule.state, 'in_progress')
        pickup = schedule.pickup_ids[0]
        pickup.action_arrive()
        pickup.action_collect(80)
        pickup.action_complete()
        self.assertEqual(pickup.state, 'completed')
        self.assertEqual(schedule.state, 'completed')

    def test_recycling_and_disposal(self):
        entry = self._make_entry(quantity=40)
        rec = self.env['wm.recycling'].create({
            'entry_id': entry.id,
            'quantity': 25,
            'material': 'Paper',
            'vendor_id': self.vendor.id,
        })
        rec.action_confirm()
        rec.action_complete()
        self.assertEqual(rec.state, 'completed')

        disp = self.env['wm.disposal'].create({
            'entry_id': entry.id,
            'quantity': 15,
            'material': 'Residual',
            'vendor_id': self.vendor.id,
            'certificate_ref': 'CERT-001',
        })
        disp.action_confirm()
        disp.action_complete()
        self.assertEqual(disp.state, 'completed')

    def test_compliance_expiry(self):
        comp = self.env['wm.compliance'].create({
            'title': 'Hazardous Authorization',
            'regulation': 'SPCB',
            'expiry_date': fields.Date.today() - timedelta(days=1),
            'state': 'valid',
        })
        comp._update_expiry_state()
        self.assertEqual(comp.state, 'expired')

    def test_audit_immutable_for_user(self):
        entry = self._make_entry()
        audit = self.env['wm.audit'].search([('res_model', '=', 'wm.entry'), ('res_id', '=', entry.id)], limit=1)
        self.assertTrue(audit)
        user = self.env['res.users'].create({
            'name': 'WM User',
            'login': 'wm_user_test_%s' % fields.Datetime.now(),
            'groups_id': [(6, 0, [self.env.ref('waste_management.group_wm_user').id])],
        })
        with self.assertRaises(UserError):
            audit.with_user(user).write({'notes': 'hacked'})

    def test_dashboard_aggregation(self):
        entry = self._make_entry(quantity=120)
        entry.action_confirm()
        data = self.Dashboard.get_dashboard_data()
        self.assertIn('kpis', data)
        self.assertGreaterEqual(data['kpis']['total_waste'], 120)
        entries = self.Dashboard.get_entries_data()
        self.assertTrue(entries['rows'])
        created = self.Dashboard.create_entry({
            'waste_type': 'Plastic',
            'category': 'Plastic',
            'amount': 15,
            'site': 'Site Beta',
            'location': 'Bay 2',
            'as_draft': False,
        })
        self.assertTrue(created.get('success'))
        self.assertTrue(created['data']['code'])

    def test_invalid_pickup_transition(self):
        entry = self._make_entry()
        schedule = self.env['wm.collection.schedule'].create({
            'entry_id': entry.id,
            'quantity': 10,
            'pickup_date': fields.Date.today(),
            'site': 'Site Alpha',
            'vendor_id': self.vendor.id,
        })
        schedule.action_schedule()
        pickup = schedule.pickup_ids[0]
        with self.assertRaises(UserError):
            pickup.action_complete()
