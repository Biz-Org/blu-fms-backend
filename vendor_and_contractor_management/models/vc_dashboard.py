# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError


class VcDashboard(models.TransientModel):
    _name = 'vc.dashboard'
    _description = 'Vendor & Contractor Dashboard API'
    _inherit = ['vc.api.mixin']

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _safe(self, fn, *args, **kwargs):
        try:
            data = fn(*args, **kwargs)
            if isinstance(data, dict) and 'success' in data:
                return data
            return self._vc_ok(data)
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))
        except Exception as err:
            return self._vc_fail(str(err) or 'Unexpected error')

    def _filters_domain(self, filters, mapping):
        domain = []
        filters = filters or {}
        for key, leaf in mapping.items():
            if filters.get(key) not in (None, False, ''):
                domain.append((leaf[0], leaf[1], filters[key]))
        if filters.get('site_id'):
            domain.append(('site_id', '=', int(filters['site_id'])))
        elif filters.get('site'):
            domain.append(('site', 'ilike', filters['site']))
        if filters.get('search'):
            # caller should extend
            pass
        return domain

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, filters=None):
        Vendor = self.env['vc.vendor']
        Contractor = self.env['vc.contractor']
        Worker = self.env['vc.worker']
        Contract = self.env['vc.contract']
        Document = self.env['vc.document']
        Pass = self.env['vc.daily.pass']
        Ptw = self.env['vc.ptw']
        Attendance = self.env['vc.attendance']
        Breach = self.env['vc.sla.breach']
        today = fields.Date.context_today(self)

        vendor_states = dict(Vendor._fields['state'].selection)
        contractor_states = dict(Contractor._fields['state'].selection)

        total_vendors = Vendor.search_count([])
        active_vendors = Vendor.search_count([('state', '=', 'active')])
        pending_vendors = Vendor.search_count([
            ('state', 'in', ('submitted', 'under_verification', 'pending_verification', 'pending_approval')),
        ])
        suspended_vendors = Vendor.search_count([('state', '=', 'suspended')])
        total_contractors = Contractor.search_count([])
        active_contractors = Contractor.search_count([('state', 'in', ('active', 'approved'))])
        pending_contractors = Contractor.search_count([
            ('state', 'in', ('draft', 'submitted', 'pending', 'under_verification')),
        ])
        total_workers = Worker.search_count([])
        active_workers = Worker.search_count([('state', '=', 'active')])
        workers_on_site = Attendance.search_count([
            ('date', '=', today),
            ('state', 'in', ('present', 'late')),
            ('check_out_dt', '=', False),
        ])
        attendance_today = Attendance.search_count([('date', '=', today)])
        active_passes = Pass.search_count([('state', '=', 'active')])
        active_ptw = Ptw.search_count([('state', 'in', ('active', 'issued'))])
        pending_ptw = Ptw.search_count([
            ('state', 'in', ('submitted', 'pending_safety', 'pending_approval')),
        ])
        expiring_contracts = Contract.search_count([('state', 'in', ('expiring', 'renewal_pending'))])
        expiring_docs = Document.search_count([('state', 'in', ('expiring', 'expired'))])
        compliance_issues = Document.search_count([
            ('state', 'in', ('expired', 'rejected', 'pending_verification')),
            ('required', '=', True),
        ])
        sla_breaches = Breach.search_count([('state', 'in', ('open', 'acknowledged'))])

        pending_rows = []
        for v in Vendor.search([
            ('state', 'in', ('submitted', 'under_verification', 'pending_verification', 'pending_approval')),
        ], limit=5):
            pending_rows.append({
                'type': 'Vendor',
                'name': v.name,
                'category': dict(v._fields['category'].selection).get(v.category, ''),
                'site': v.site or (v.site_id.name if v.site_id else ''),
                'action': 'Approval / Verification',
                'due': fields.Date.to_string(v.registration_date) if v.registration_date else '',
                'status': vendor_states.get(v.state, v.state),
            })
        for c in Contractor.search([
            ('state', 'in', ('draft', 'submitted', 'pending', 'under_verification')),
        ], limit=5):
            pending_rows.append({
                'type': 'Contractor',
                'name': c.name,
                'category': c.work_category or c.contractor_type or '',
                'site': c.site or (c.site_id.name if c.site_id else ''),
                'action': 'Approval',
                'due': '',
                'status': contractor_states.get(c.state, c.state),
            })

        # Charts
        vendor_dist = []
        for state, label in vendor_states.items():
            count = Vendor.search_count([('state', '=', state)])
            if count:
                vendor_dist.append({'state': state, 'label': label, 'count': count})
        contractor_dist = []
        for state, label in contractor_states.items():
            count = Contractor.search_count([('state', '=', state)])
            if count:
                contractor_dist.append({'state': state, 'label': label, 'count': count})

        # Monthly onboarding (last 6 months)
        onboarding = []
        for i in range(5, -1, -1):
            month_start = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
            onboarding.append({
                'month': month_start.strftime('%Y-%m'),
                'vendors': Vendor.search_count([
                    ('registration_date', '>=', month_start),
                    ('registration_date', '<=', month_end),
                ]),
                'contractors': Contractor.search_count([
                    ('create_date', '>=', fields.Datetime.to_datetime(month_start)),
                    ('create_date', '<=', fields.Datetime.to_datetime(month_end) + timedelta(days=1)),
                ]),
            })

        attendance_trend = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            attendance_trend.append({
                'date': fields.Date.to_string(day),
                'count': Attendance.search_count([('date', '=', day)]),
            })

        # Compatibility payload (legacy keys) + expanded KPIs
        return {
            'kpis': {
                'total_vendors': total_vendors,
                'active_vendors': active_vendors,
                'active_contractors': active_contractors,
                'approved_contractors': active_contractors,
                'pending_approvals': pending_vendors + pending_contractors,
                'compliance_issues': compliance_issues,
                'expiring_soon': expiring_contracts + expiring_docs,
                'workers_on_site': workers_on_site,
                'pending_vendors': pending_vendors,
                'suspended_vendors': suspended_vendors,
                'total_contractors': total_contractors,
                'pending_contractors': pending_contractors,
                'suspended_contractors': Contractor.search_count([('state', '=', 'suspended')]),
                'total_workers': total_workers,
                'active_workers': active_workers,
                'attendance_today': attendance_today,
                'active_passes': active_passes,
                'active_daily_passes': active_passes,
                'active_ptw': active_ptw,
                'pending_ptw': pending_ptw,
                'expiring_contracts': expiring_contracts,
                'expiring_documents': expiring_docs,
                'sla_breaches': sla_breaches,
            },
            'pending_actions': pending_rows,
            'alerts': [
                {'title': 'Contract Expiry', 'text': '%s contracts need renewal attention.' % expiring_contracts},
                {'title': 'Compliance Incomplete', 'text': '%s documents expiring or expired.' % expiring_docs},
                {'title': 'SLA / Performance', 'text': '%s open SLA breaches.' % sla_breaches},
            ],
            'charts': {
                'vendor_status': vendor_dist,
                'contractor_status': contractor_dist,
                'monthly_onboarding': onboarding,
                'attendance_trend': attendance_trend,
                'compliance_summary': {
                    'issues': compliance_issues,
                    'expiring_docs': expiring_docs,
                    'expiring_contracts': expiring_contracts,
                },
            },
        }

    # ------------------------------------------------------------------
    # Vendors / Contractors / Workforce (legacy-compatible list APIs)
    # ------------------------------------------------------------------
    @api.model
    def get_vendors_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('search'):
            domain += ['|', ('name', 'ilike', filters['search']), ('code', 'ilike', filters['search'])]
        rows = []
        for v in self.env['vc.vendor'].search(domain, limit=int(filters.get('limit') or 200)):
            rows.append({
                'id': v.id,
                'code': v.code,
                'name': v.name,
                'category': dict(v._fields['category'].selection).get(v.category, ''),
                'contact': v.contact_person or '',
                'email': v.email or '',
                'phone': v.phone or '',
                'site': v.site or (v.site_id.name if v.site_id else ''),
                'contract_label': 'AMC Active' if v.contract_ids.filtered(lambda c: c.is_amc and c.state == 'active') else '—',
                'compliance': dict(v._fields['compliance_state'].selection).get(v.compliance_state, ''),
                'compliance_key': v.compliance_state,
                'document_status': v.document_status,
                'rating': v.rating,
                'state': v.state,
                'state_label': dict(v._fields['state'].selection).get(v.state, v.state),
            })
        return {
            'kpis': {
                'total': self.env['vc.vendor'].search_count([]),
                'active': self.env['vc.vendor'].search_count([('state', '=', 'active')]),
                'pending': self.env['vc.vendor'].search_count([
                    ('state', 'in', ('submitted', 'under_verification', 'pending_approval', 'pending_verification')),
                ]),
                'expiring': self.env['vc.vendor'].search_count([('state', 'in', ('expired', 'suspended'))]),
            },
            'rows': rows,
        }

    @api.model
    def get_contractors_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('search'):
            domain += ['|', ('name', 'ilike', filters['search']), ('code', 'ilike', filters['search'])]
        rows = []
        for c in self.env['vc.contractor'].search(domain, limit=int(filters.get('limit') or 200)):
            rows.append({
                'id': c.id,
                'code': c.code,
                'name': c.name,
                'type': dict(c._fields['contractor_type'].selection).get(c.contractor_type, ''),
                'category': c.work_category or c.specialization or '',
                'contact': c.contact_person or '',
                'vendor': c.vendor_id.name or '',
                'site': c.site or (c.site_id.name if c.site_id else ''),
                'workers': len(c.worker_ids),
                'compliance': dict(c._fields['compliance_state'].selection).get(c.compliance_state, ''),
                'state': c.state,
                'state_label': dict(c._fields['state'].selection).get(c.state, c.state),
            })
        return {
            'kpis': {
                'total': self.env['vc.contractor'].search_count([]),
                'active': self.env['vc.contractor'].search_count([('state', 'in', ('active', 'approved'))]),
                'pending': self.env['vc.contractor'].search_count([
                    ('state', 'in', ('draft', 'submitted', 'pending', 'under_verification')),
                ]),
                'suspended': self.env['vc.contractor'].search_count([('state', '=', 'suspended')]),
            },
            'rows': rows,
        }

    @api.model
    def get_contracts_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('is_amc') is not None:
            domain.append(('is_amc', '=', bool(filters['is_amc'])))
        rows = []
        for c in self.env['vc.contract'].search(domain, limit=int(filters.get('limit') or 200)):
            rows.append(c.to_api_dict())
        return {
            'kpis': {
                'active': self.env['vc.contract'].search_count([('state', '=', 'active')]),
                'expiring': self.env['vc.contract'].search_count([('state', '=', 'expiring')]),
                'expired': self.env['vc.contract'].search_count([('state', '=', 'expired')]),
                'amc': self.env['vc.contract'].search_count([('is_amc', '=', True)]),
            },
            'rows': rows,
        }

    @api.model
    def get_contract_detail(self, contract_id):
        contract = self.env['vc.contract'].browse(int(contract_id))
        if not contract.exists():
            return self._vc_fail('Contract not found')
        data = contract.to_api_dict()
        data['renewals'] = [{
            'id': r.id,
            'previous_end_date': self._vc_date(r.previous_end_date),
            'new_end_date': self._vc_date(r.new_end_date),
            'notes': r.notes or '',
            'user': r.user_id.name,
            'renewal_date': self._vc_date(r.renewal_date),
        } for r in contract.renewal_ids]
        data['breaches'] = [{
            'id': b.id,
            'name': b.name,
            'sla_type': b.sla_type,
            'severity': b.severity,
            'state': b.state,
            'breach_date': self._vc_datetime(b.breach_date),
        } for b in contract.breach_ids]
        return self._vc_ok(data)

    @api.model
    def create_contract(self, values):
        values = values or {}
        try:
            contract = self.env['vc.contract'].create(values)
            return self._vc_ok(contract.to_api_dict(), 'Contract created')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def approve_contract(self, contract_id):
        try:
            contract = self.env['vc.contract'].browse(int(contract_id))
            contract.action_approve()
            return self._vc_ok(contract.to_api_dict(), 'Contract approved')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def renew_contract(self, contract_id, values=None):
        try:
            contract = self.env['vc.contract'].browse(int(contract_id))
            contract.action_renew(values or {})
            return self._vc_ok(contract.to_api_dict(), 'Contract renewed')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def submit_renewal(self, contract_id, values=None):
        try:
            contract = self.env['vc.contract'].browse(int(contract_id))
            self._vc_assert_transition(
                contract, ('active', 'expiring', 'expired', 'renewal_pending'), 'submit renewal'
            )
            contract.write({
                'state': 'renewal_pending',
                'renewal_notes': (values or {}).get('renewal_notes') or contract.renewal_notes,
            })
            return self._vc_ok(contract.to_api_dict(), 'Renewal submitted')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def get_workforce_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('contractor_id'):
            domain.append(('contractor_id', '=', int(filters['contractor_id'])))
        if filters.get('search'):
            domain += ['|', ('name', 'ilike', filters['search']), ('code', 'ilike', filters['search'])]
        rows = []
        for w in self.env['vc.worker'].search(domain, limit=int(filters.get('limit') or 300)):
            rows.append({
                'id': w.id,
                'code': w.code,
                'name': w.name,
                'contractor': w.contractor_id.name or '',
                'vendor': w.vendor_id.name or '',
                'skill': w.skill or w.skills or '',
                'role': w.role or '',
                'site': w.site or (w.site_id.name if w.site_id else ''),
                'state': w.state,
                'state_label': dict(w._fields['state'].selection).get(w.state, w.state),
                'document_status': w.document_status,
                'document_label': dict(w._fields['document_status'].selection).get(w.document_status, ''),
                'compliance_state': w.compliance_state,
            })
        return {
            'kpis': {
                'total': self.env['vc.worker'].search_count([]),
                'active': self.env['vc.worker'].search_count([('state', '=', 'active')]),
                'on_leave': self.env['vc.worker'].search_count([('state', '=', 'on_leave')]),
                'inactive': self.env['vc.worker'].search_count([('state', '=', 'inactive')]),
                'expiring_docs': self.env['vc.worker'].search_count([
                    ('document_status', 'in', ('expiring', 'expired', 'missing')),
                ]),
            },
            'rows': rows,
        }

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    @api.model
    def get_documents_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('vendor_id'):
            domain.append(('vendor_id', '=', int(filters['vendor_id'])))
        if filters.get('contractor_id'):
            domain.append(('contractor_id', '=', int(filters['contractor_id'])))
        if filters.get('worker_id'):
            domain.append(('worker_id', '=', int(filters['worker_id'])))
        rows = [d.to_api_dict() for d in self.env['vc.document'].search(domain, limit=int(filters.get('limit') or 300))]
        return {
            'kpis': {
                'total': self.env['vc.document'].search_count([]),
                'verified': self.env['vc.document'].search_count([('state', 'in', ('verified', 'expiring'))]),
                'pending': self.env['vc.document'].search_count([
                    ('state', 'in', ('pending_verification', 'submitted', 'under_verification', 'draft')),
                ]),
                'expiring': self.env['vc.document'].search_count([('state', '=', 'expiring')]),
                'expired': self.env['vc.document'].search_count([('state', '=', 'expired')]),
            },
            'rows': rows,
        }

    @api.model
    def upload_document(self, values):
        values = values or {}
        try:
            if values.get('attachment_datas') and not values.get('attachment'):
                values['attachment'] = values.pop('attachment_datas')
            doc = self.env['vc.document'].create(values)
            if values.get('submit'):
                doc.action_submit_for_verification()
            return self._vc_ok(doc.to_api_dict(), 'Document uploaded')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def get_vendor_documents(self, vendor_id):
        return self._vc_ok(self.get_documents_data({'vendor_id': vendor_id}))

    @api.model
    def get_contractor_documents(self, contractor_id):
        return self._vc_ok(self.get_documents_data({'contractor_id': contractor_id}))

    @api.model
    def get_worker_documents(self, worker_id):
        return self._vc_ok(self.get_documents_data({'worker_id': worker_id}))

    @api.model
    def get_compliance_summary(self, filters=None):
        filters = filters or {}
        Document = self.env['vc.document']
        domain = []
        if filters.get('vendor_id'):
            domain.append(('vendor_id', '=', int(filters['vendor_id'])))
        if filters.get('contractor_id'):
            domain.append(('contractor_id', '=', int(filters['contractor_id'])))
        docs = Document.search(domain)
        required = docs.filtered('required')
        verified = required.filtered(lambda d: d.state in ('verified', 'expiring'))
        return self._vc_ok({
            'total_documents': len(docs),
            'required': len(required),
            'verified_required': len(verified),
            'pending': len(required) - len(verified),
            'expired': len(docs.filtered(lambda d: d.state == 'expired')),
            'expiring': len(docs.filtered(lambda d: d.state == 'expiring')),
            'compliance_pct': round((len(verified) / len(required) * 100.0), 2) if required else 0.0,
        })

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------
    @api.model
    def get_attendance_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('worker_id'):
            domain.append(('worker_id', '=', int(filters['worker_id'])))
        if filters.get('date_from'):
            domain.append(('date', '>=', filters['date_from']))
        if filters.get('date_to'):
            domain.append(('date', '<=', filters['date_to']))
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        rows = []
        for a in self.env['vc.attendance'].search(domain, limit=int(filters.get('limit') or 200), order='date desc, id desc'):
            rows.append(a.to_api_dict())
        return {
            'kpis': {
                'total': self.env['vc.worker'].search_count([]),
                'present': self.env['vc.attendance'].search_count([
                    ('date', '=', fields.Date.context_today(self)),
                    ('state', 'in', ('present', 'late')),
                ]),
                'absent': self.env['vc.attendance'].search_count([
                    ('date', '=', fields.Date.context_today(self)),
                    ('state', '=', 'absent'),
                ]),
                'late': self.env['vc.attendance'].search_count([
                    ('date', '=', fields.Date.context_today(self)),
                    ('state', '=', 'late'),
                ]),
                'on_leave': self.env['vc.attendance'].search_count([
                    ('date', '=', fields.Date.context_today(self)),
                    ('state', '=', 'on_leave'),
                ]),
                'on_site': self.env['vc.attendance'].search_count([
                    ('date', '=', fields.Date.context_today(self)),
                    ('state', 'in', ('present', 'late')),
                    ('check_out_dt', '=', False),
                ]),
            },
            'rows': rows,
        }

    @api.model
    def check_in_worker(self, worker_id, site_id=False, values=None):
        try:
            att = self.env['vc.attendance'].check_in_worker(worker_id, site_id=site_id, values=values or {})
            return self._vc_ok(att.to_api_dict(), 'Checked in')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def check_out_worker(self, attendance_id, values=None):
        try:
            att = self.env['vc.attendance'].browse(int(attendance_id))
            if values and values.get('exit_gate'):
                att.exit_gate = values['exit_gate']
            att.action_check_out()
            return self._vc_ok(att.to_api_dict(), 'Checked out')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def get_worker_attendance(self, worker_id):
        return self._vc_ok(self.get_attendance_data({'worker_id': worker_id}))

    @api.model
    def get_attendance_summary(self, filters=None):
        data = self.get_attendance_data(filters)
        return self._vc_ok(data.get('kpis', {}))

    # ------------------------------------------------------------------
    # Daily Pass
    # ------------------------------------------------------------------
    @api.model
    def get_passes_data(self, filters=None):
        return self.get_daily_pass_data(filters)

    @api.model
    def get_daily_pass_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        rows = [p.to_api_dict() for p in self.env['vc.daily.pass'].search(domain, limit=int(filters.get('limit') or 200))]
        return {
            'kpis': {
                'total': self.env['vc.daily.pass'].search_count([]),
                'active': self.env['vc.daily.pass'].search_count([('state', '=', 'active')]),
                'pending': self.env['vc.daily.pass'].search_count([
                    ('state', 'in', ('requested', 'draft', 'submitted')),
                ]),
                'expiring': self.env['vc.daily.pass'].search_count([('state', '=', 'active')]),
                'expired': self.env['vc.daily.pass'].search_count([('state', '=', 'expired')]),
            },
            'rows': rows,
        }

    @api.model
    def create_daily_pass(self, values):
        try:
            rec = self.env['vc.daily.pass'].create(values or {})
            return self._vc_ok(rec.to_api_dict(), 'Daily pass created')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def approve_daily_pass(self, pass_id):
        try:
            rec = self.env['vc.daily.pass'].browse(int(pass_id))
            rec.action_approve()
            return self._vc_ok(rec.to_api_dict(), 'Daily pass approved')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def cancel_daily_pass(self, pass_id):
        try:
            rec = self.env['vc.daily.pass'].browse(int(pass_id))
            rec.action_cancel()
            return self._vc_ok(rec.to_api_dict(), 'Daily pass cancelled')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    # ------------------------------------------------------------------
    # PTW
    # ------------------------------------------------------------------
    @api.model
    def get_ptw_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        rows = [p.to_api_dict() for p in self.env['vc.ptw'].search(domain, limit=int(filters.get('limit') or 200))]
        return {
            'kpis': {
                'total': self.env['vc.ptw'].search_count([]),
                'active': self.env['vc.ptw'].search_count([('state', 'in', ('active', 'issued'))]),
                'pending': self.env['vc.ptw'].search_count([
                    ('state', 'in', ('pending_approval', 'pending_safety', 'draft', 'submitted')),
                ]),
                'expiring': self.env['vc.ptw'].search_count([('state', '=', 'active')]),
                'expired': self.env['vc.ptw'].search_count([('state', '=', 'expired')]),
                'rejected': self.env['vc.ptw'].search_count([('state', '=', 'rejected')]),
            },
            'rows': rows,
        }

    @api.model
    def get_ptw_detail(self, ptw_id):
        rec = self.env['vc.ptw'].browse(int(ptw_id))
        if not rec.exists():
            return self._vc_fail('PTW not found')
        data = rec.to_api_dict()
        data.update({
            'work_description': rec.work_description or '',
            'safety_checklist': rec.safety_checklist or '',
            'ppe_checklist': rec.ppe_checklist or '',
            'isolation_requirements': rec.isolation_requirements or '',
            'emergency_precautions': rec.emergency_precautions or '',
            'closure_details': rec.closure_details or '',
        })
        return self._vc_ok(data)

    @api.model
    def create_ptw(self, values):
        try:
            vals = dict(values or {})
            worker_ids = vals.pop('worker_ids', None)
            if worker_ids:
                vals['worker_ids'] = [(6, 0, worker_ids)]
            rec = self.env['vc.ptw'].create(vals)
            return self._vc_ok(rec.to_api_dict(), 'PTW created')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def submit_ptw(self, ptw_id):
        try:
            rec = self.env['vc.ptw'].browse(int(ptw_id))
            rec.action_submit()
            return self._vc_ok(rec.to_api_dict(), 'PTW submitted')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def verify_ptw(self, ptw_id):
        try:
            rec = self.env['vc.ptw'].browse(int(ptw_id))
            rec.action_safety_verify()
            return self._vc_ok(rec.to_api_dict(), 'PTW safety verified')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def issue_ptw(self, ptw_id):
        try:
            rec = self.env['vc.ptw'].browse(int(ptw_id))
            if rec.state == 'approved':
                rec.action_issue()
            elif rec.state == 'issued':
                rec.action_start_work()
            else:
                rec.action_approve()
                rec.action_issue()
            return self._vc_ok(rec.to_api_dict(), 'PTW issued')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def close_ptw(self, ptw_id):
        try:
            rec = self.env['vc.ptw'].browse(int(ptw_id))
            rec.action_close()
            return self._vc_ok(rec.to_api_dict(), 'PTW closed')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    # ------------------------------------------------------------------
    # Performance
    # ------------------------------------------------------------------
    @api.model
    def get_performance_data(self, filters=None):
        filters = filters or {}
        domain = [('state', '=', 'submitted')]
        if filters.get('vendor_id'):
            domain.append(('vendor_id', '=', int(filters['vendor_id'])))
        if filters.get('contractor_id'):
            domain.append(('contractor_id', '=', int(filters['contractor_id'])))
        rows = [e.to_api_dict() for e in self.env['vc.evaluation'].search(domain, limit=200)]
        rating_dist = defaultdict(int)
        for r in rows:
            rating_dist[r.get('rating') or 'poor'] += 1
        return self._vc_ok({
            'rows': rows,
            'rating_distribution': dict(rating_dist),
            'kpis': {
                'total': len(rows),
                'avg_score': round(sum(r['overall_score'] for r in rows) / len(rows), 2) if rows else 0.0,
            },
        })

    @api.model
    def submit_evaluation(self, values):
        try:
            rec = self.env['vc.evaluation'].create(values or {})
            rec.action_submit()
            return self._vc_ok(rec.to_api_dict(), 'Evaluation submitted')
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def get_vendor_performance(self, vendor_id):
        return self.get_performance_data({'vendor_id': vendor_id})

    @api.model
    def get_contractor_performance(self, contractor_id):
        return self.get_performance_data({'contractor_id': contractor_id})

    # ------------------------------------------------------------------
    # Activity / Notifications
    # ------------------------------------------------------------------
    @api.model
    def get_activity_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('activity_type'):
            domain.append(('activity_type', '=', filters['activity_type']))
        if filters.get('res_model'):
            domain.append(('res_model', '=', filters['res_model']))
        if filters.get('res_id'):
            domain.append(('res_id', '=', int(filters['res_id'])))
        rows = []
        for a in self.env['vc.activity'].search(domain, limit=int(filters.get('limit') or 200)):
            rows.append({
                'id': a.id,
                'code': a.name,
                'activity_type': a.activity_type,
                'res_model': a.res_model,
                'res_id': a.res_id,
                'res_name': a.res_name,
                'user': a.user_id.name,
                'datetime': self._vc_datetime(a.event_datetime),
                'site': a.site_id.name if a.site_id else '',
                'description': a.description or '',
                'previous_state': a.previous_state or '',
                'new_state': a.new_state or '',
            })
        return self._vc_ok({'rows': rows})

    @api.model
    def get_record_activity(self, model, record_id):
        return self.get_activity_data({'res_model': model, 'res_id': record_id})

    @api.model
    def get_notifications_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get('is_read') is not None:
            domain.append(('is_read', '=', bool(filters['is_read'])))
        if filters.get('category'):
            domain.append(('category', '=', filters['category']))
        rows = []
        for n in self.env['vc.notification'].search(domain, limit=int(filters.get('limit') or 100)):
            rows.append({
                'id': n.id,
                'title': n.title,
                'message': n.message or '',
                'category': n.category,
                'severity': n.severity,
                'is_read': n.is_read,
                'res_model': n.res_model,
                'res_id': n.res_id,
                'create_date': self._vc_datetime(n.create_date),
            })
        return self._vc_ok({'rows': rows})

    @api.model
    def mark_notification_read(self, notification_id):
        rec = self.env['vc.notification'].browse(int(notification_id))
        if not rec.exists():
            return self._vc_fail('Notification not found')
        rec.action_mark_read()
        return self._vc_ok({'id': rec.id, 'is_read': True})

    @api.model
    def get_notification_summary(self):
        Notification = self.env['vc.notification']
        return self._vc_ok({
            'total': Notification.search_count([]),
            'unread': Notification.search_count([('is_read', '=', False)]),
            'critical': Notification.search_count([('severity', '=', 'critical'), ('is_read', '=', False)]),
        })

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    @api.model
    def get_report_catalog(self):
        catalog = [
            {'type': 'vendor_master', 'name': 'Vendor Master Report'},
            {'type': 'contractor_master', 'name': 'Contractor Master Report'},
            {'type': 'workforce', 'name': 'Workforce Report'},
            {'type': 'contract', 'name': 'Contract Report'},
            {'type': 'amc', 'name': 'AMC Report'},
            {'type': 'attendance', 'name': 'Attendance Report'},
            {'type': 'daily_pass', 'name': 'Daily Pass Report'},
            {'type': 'ptw', 'name': 'PTW Report'},
            {'type': 'compliance', 'name': 'Compliance Report'},
            {'type': 'document_expiry', 'name': 'Document Expiry Report'},
            {'type': 'performance', 'name': 'Performance Report'},
            {'type': 'sla', 'name': 'SLA Report'},
            {'type': 'activity', 'name': 'Activity / Audit Report'},
        ]
        return self._vc_ok({'catalog': catalog})

    @api.model
    def get_reports_data(self, filters=None):
        return self.get_report_catalog()

    @api.model
    def generate_report(self, report_type, filters=None):
        filters = filters or {}
        try:
            if report_type == 'vendor_master':
                data = self.get_vendors_data(filters)
            elif report_type == 'contractor_master':
                data = self.get_contractors_data(filters)
            elif report_type == 'workforce':
                data = self.get_workforce_data(filters)
            elif report_type == 'contract':
                data = self.get_contracts_data(filters)
            elif report_type == 'amc':
                data = self.get_contracts_data({**filters, 'is_amc': True})
            elif report_type == 'attendance':
                data = self.get_attendance_data(filters)
            elif report_type == 'daily_pass':
                data = self.get_daily_pass_data(filters)
            elif report_type == 'ptw':
                data = self.get_ptw_data(filters)
            elif report_type == 'compliance':
                data = self.get_compliance_summary(filters).get('data', {})
            elif report_type == 'document_expiry':
                data = self.get_documents_data({**filters, 'state': filters.get('state') or 'expiring'})
            elif report_type == 'performance':
                data = self.get_performance_data(filters).get('data', {})
            elif report_type == 'sla':
                breaches = self.env['vc.sla.breach'].search([], limit=200)
                total = len(breaches)
                open_b = len(breaches.filtered(lambda b: b.state in ('open', 'acknowledged')))
                data = {
                    'total_sla_events': total,
                    'sla_breached': open_b,
                    'sla_met': max(total - open_b, 0),
                    'compliance_pct': round(((total - open_b) / total * 100.0), 2) if total else 100.0,
                    'rows': [{
                        'id': b.id,
                        'name': b.name,
                        'contract': b.contract_id.name,
                        'sla_type': b.sla_type,
                        'severity': b.severity,
                        'state': b.state,
                        'breach_date': self._vc_datetime(b.breach_date),
                    } for b in breaches],
                }
            elif report_type == 'activity':
                data = self.get_activity_data(filters).get('data', {})
            else:
                return self._vc_fail('Unknown report type: %s' % report_type)
            return self._vc_ok({'report_type': report_type, 'result': data})
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    # ------------------------------------------------------------------
    # Workflow action helpers for frontend
    # ------------------------------------------------------------------
    @api.model
    def vendor_action(self, vendor_id, action, values=None):
        try:
            rec = self.env['vc.vendor'].browse(int(vendor_id))
            if values:
                rec.write(values)
            method = getattr(rec, 'action_%s' % action, None)
            if not method:
                return self._vc_fail('Unknown vendor action')
            method()
            return self._vc_ok({'id': rec.id, 'state': rec.state}, 'Vendor %s done' % action)
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def contractor_action(self, contractor_id, action, values=None):
        try:
            rec = self.env['vc.contractor'].browse(int(contractor_id))
            if values:
                rec.write(values)
            mapping = {
                'submit': 'action_submit',
                'start_verification': 'action_start_verification',
                'verify': 'action_start_verification',
                'approve': 'action_approve',
                'reject': 'action_reject',
                'activate': 'action_activate',
                'suspend': 'action_suspend',
                'reactivate': 'action_reactivate',
            }
            method_name = mapping.get(action)
            if not method_name:
                return self._vc_fail('Unknown contractor action')
            getattr(rec, method_name)()
            return self._vc_ok({'id': rec.id, 'state': rec.state}, 'Contractor %s done' % action)
        except (UserError, ValidationError, AccessError) as err:
            return self._vc_fail(str(err))

    @api.model
    def get_sites_data(self, filters=None):
        rows = []
        for s in self.env['vc.site'].search([], limit=200):
            rows.append({
                'id': s.id,
                'code': s.code,
                'name': s.name,
                'address': s.address or '',
                'manager': s.manager_id.name if s.manager_id else '',
                'phone': s.phone or '',
                'active': s.active,
            })
        return self._vc_ok({'rows': rows})
