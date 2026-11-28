# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'vendor_contractor')
class TestVcWorkflows(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['vc.site'].create({
            'name': 'Test Site Alpha',
            'address': '1 Test Road',
        })
        cls.Dashboard = cls.env['vc.dashboard']

    def _make_vendor(self, **kwargs):
        vals = {
            'name': 'Test Vendor Co',
            'contact_person': 'Alice Tester',
            'site_id': self.site.id,
            'gstin': '27AABCT1332L1ZV',
            'pan': 'AABCT1332L',
        }
        vals.update(kwargs)
        return self.env['vc.vendor'].create(vals)

    def _make_mandatory_doc(self, **kwargs):
        vals = {
            'name': 'Trade License',
            'document_type': 'license',
            'required': True,
            'has_expiry': True,
            'expiry_date': fields.Date.today() + timedelta(days=120),
            'attachment': b'JVBERi0xLjQ=',  # minimal placeholder
            'attachment_name': 'license.pdf',
            'state': 'draft',
        }
        vals.update(kwargs)
        doc = self.env['vc.document'].create(vals)
        doc.action_submit_for_verification()
        doc.action_verify()
        return doc

    def test_vendor_lifecycle(self):
        vendor = self._make_vendor()
        self.assertEqual(vendor.state, 'draft')
        vendor.action_submit()
        self.assertEqual(vendor.state, 'submitted')
        vendor.action_verify()
        self.assertEqual(vendor.state, 'under_verification')
        vendor.action_approve()
        self.assertEqual(vendor.state, 'approved')
        self.assertTrue(vendor.approved_by_id)
        self.assertTrue(vendor.approval_date)
        with self.assertRaises(UserError):
            vendor.action_activate()
        self._make_mandatory_doc(vendor_id=vendor.id)
        vendor.invalidate_recordset()
        vendor.action_activate()
        self.assertEqual(vendor.state, 'active')
        vendor.action_suspend()
        self.assertEqual(vendor.state, 'suspended')
        vendor.action_reactivate()
        self.assertEqual(vendor.state, 'active')

    def test_vendor_reject_requires_reason(self):
        vendor = self._make_vendor()
        vendor.action_submit()
        with self.assertRaises(UserError):
            vendor.action_reject()
        vendor.rejection_reason = 'Incomplete paperwork'
        vendor.action_reject()
        self.assertEqual(vendor.state, 'rejected')

    def test_vendor_invalid_gstin(self):
        with self.assertRaises(ValidationError):
            self._make_vendor(gstin='INVALID')

    def test_vendor_duplicate_pan(self):
        self._make_vendor(name='V1', pan='AABCT1332L', gstin=False)
        with self.assertRaises(ValidationError):
            self._make_vendor(name='V2', pan='AABCT1332L', gstin=False)

    def test_contractor_and_worker(self):
        vendor = self._make_vendor()
        vendor.action_submit()
        vendor.action_verify()
        vendor.action_approve()
        self._make_mandatory_doc(vendor_id=vendor.id)
        vendor.action_activate()

        contractor = self.env['vc.contractor'].create({
            'name': 'Test Contractor',
            'contact_person': 'Bob Builder',
            'vendor_id': vendor.id,
            'site_id': self.site.id,
        })
        contractor.action_submit()
        contractor.action_start_verification()
        contractor.verification_complete = True
        contractor.action_approve()
        self._make_mandatory_doc(contractor_id=contractor.id)
        contractor.action_activate()
        self.assertTrue(contractor.is_operational())

        worker = self.env['vc.worker'].create({
            'name': 'Worker One',
            'contractor_id': contractor.id,
            'site_id': self.site.id,
            'skill': 'Electrician',
        })
        worker.action_submit()
        self._make_mandatory_doc(worker_id=worker.id)
        worker.action_activate()
        self.assertEqual(worker.state, 'active')
        ok, _ = worker.is_eligible_for_access(site_id=self.site.id)
        self.assertTrue(ok)

    def test_attendance_check_in_out(self):
        vendor = self._make_vendor()
        vendor.write({'state': 'active'})
        contractor = self.env['vc.contractor'].create({
            'name': 'Att Contractor',
            'contact_person': 'C1',
            'vendor_id': vendor.id,
            'site_id': self.site.id,
            'state': 'active',
            'verification_complete': True,
        })
        worker = self.env['vc.worker'].create({
            'name': 'Att Worker',
            'contractor_id': contractor.id,
            'site_id': self.site.id,
            'state': 'active',
        })
        self._make_mandatory_doc(worker_id=worker.id)
        self._make_mandatory_doc(contractor_id=contractor.id)

        att = self.env['vc.attendance'].check_in_worker(worker.id, site_id=self.site.id)
        self.assertEqual(att.state, 'present')
        with self.assertRaises(UserError):
            self.env['vc.attendance'].check_in_worker(worker.id, site_id=self.site.id)
        att.action_check_out()
        self.assertEqual(att.state, 'checked_out')

    def test_contract_renew_and_terminate(self):
        vendor = self._make_vendor(state='active')
        contract = self.env['vc.contract'].create({
            'name': 'AMC Test',
            'vendor_id': vendor.id,
            'site_id': self.site.id,
            'date_start': fields.Date.today(),
            'date_end': fields.Date.today() + timedelta(days=30),
            'is_amc': True,
            'value': 1000,
        })
        contract.action_submit()
        contract.action_approve()
        contract.action_activate()
        new_end = fields.Date.today() + timedelta(days=365)
        contract.action_renew({'date_end': fields.Date.to_string(new_end)})
        self.assertEqual(contract.state, 'renewed')
        self.assertTrue(contract.renewal_ids)
        contract.termination_reason = 'Scope complete'
        contract.action_terminate()
        self.assertEqual(contract.state, 'terminated')

    def test_daily_pass_and_ptw(self):
        contractor = self.env['vc.contractor'].create({
            'name': 'Pass Contractor',
            'contact_person': 'P1',
            'site_id': self.site.id,
            'state': 'active',
            'verification_complete': True,
        })
        daily = self.env['vc.daily.pass'].create({
            'visitor_name': 'Visitor X',
            'site': self.site.name,
            'site_id': self.site.id,
            'contractor_id': contractor.id,
            'purpose': 'Inspection',
            'validity_date': fields.Date.today(),
        })
        daily.action_submit()
        daily.action_approve()
        daily.action_activate()
        self.assertEqual(daily.state, 'active')
        daily.action_cancel()
        self.assertEqual(daily.state, 'cancelled')

        ptw = self.env['vc.ptw'].create({
            'work_activity': 'Hot Work Test',
            'permit_type': 'hot_work',
            'contractor_id': contractor.id,
            'site_id': self.site.id,
            'site': self.site.name,
            'safety_checklist': 'Fire watch ready',
            'ppe_checklist': 'Helmet, gloves',
            'ppe_compliant': True,
            'date_start': fields.Datetime.now(),
            'date_end': fields.Datetime.now() + timedelta(hours=8),
        })
        ptw.action_submit()
        ptw.action_safety_verify()
        ptw.action_approve()
        ptw.action_issue()
        ptw.action_start_work()
        self.assertEqual(ptw.state, 'active')
        ptw.action_close()
        self.assertEqual(ptw.state, 'closed')

    def test_evaluation_rating_bands(self):
        vendor = self._make_vendor(state='active')
        evaluation = self.env['vc.evaluation'].create({
            'vendor_id': vendor.id,
            'quality_score': 90,
            'safety_score': 90,
            'sla_score': 90,
            'compliance_score': 90,
            'attendance_score': 90,
        })
        self.assertEqual(evaluation.rating, 'excellent')
        evaluation.action_submit()
        self.assertEqual(evaluation.state, 'submitted')
        poor = self.env['vc.evaluation'].create({
            'vendor_id': vendor.id,
            'quality_score': 20,
            'safety_score': 20,
            'sla_score': 20,
            'compliance_score': 20,
            'attendance_score': 20,
        })
        self.assertEqual(poor.rating, 'poor')

    def test_document_expiry_cron(self):
        vendor = self._make_vendor(state='active')
        doc = self.env['vc.document'].create({
            'name': 'Expired Doc',
            'vendor_id': vendor.id,
            'required': True,
            'has_expiry': True,
            'expiry_date': fields.Date.today() - timedelta(days=1),
            'attachment': b'AAA=',
            'attachment_name': 'x.pdf',
            'state': 'verified',
        })
        self.env['vc.document'].cron_scan_expiry()
        self.assertEqual(doc.state, 'expired')

    def test_dashboard_apis(self):
        self._make_vendor(state='active')
        dash = self.Dashboard.get_dashboard_data()
        self.assertIn('kpis', dash)
        self.assertGreaterEqual(dash['kpis']['total_vendors'], 1)
        vendors = self.Dashboard.get_vendors_data()
        self.assertIn('rows', vendors)
        catalog = self.Dashboard.get_report_catalog()
        self.assertTrue(catalog.get('success'))
        report = self.Dashboard.generate_report('vendor_master', {})
        self.assertTrue(report.get('success'))

    def test_audit_immutable_for_user(self):
        vendor = self._make_vendor()
        activity = self.env['vc.activity'].sudo().search([
            ('res_model', '=', 'vc.vendor'),
            ('res_id', '=', vendor.id),
        ], limit=1)
        self.assertTrue(activity)
        # Manager can write; simulate non-manager via Access by clearing groups is heavy —
        # ensure unlink blocked without manager when not sudo: use a fresh env if possible.
        user = self.env['res.users'].create({
            'name': 'VC User',
            'login': 'vc_user_test_%s' % fields.Datetime.now().timestamp(),
            'groups_id': [(6, 0, [self.env.ref('vendor_and_contractor_management.group_vc_user').id])],
        })
        with self.assertRaises(UserError):
            activity.with_user(user).write({'description': 'hack'})
