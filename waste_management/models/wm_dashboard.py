# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.osv import expression


class WmDashboard(models.TransientModel):
    _name = 'wm.dashboard'
    _description = 'Waste Management Dashboard API'
    _inherit = ['wm.api.mixin']

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _safe(self, fn, *args, **kwargs):
        try:
            data = fn(*args, **kwargs)
            if isinstance(data, dict) and 'success' in data:
                return data
            return self._wm_ok(data)
        except (UserError, ValidationError, AccessError) as err:
            return self._wm_fail(str(err))
        except Exception as err:
            return self._wm_fail(str(err) or 'Unexpected error')

    def _fmt_kg(self, value):
        value = value or 0.0
        if value >= 1000:
            return '%s kg' % ('{:,.0f}'.format(value))
        return '%s kg' % ('{:,.1f}'.format(value).rstrip('0').rstrip('.') if value % 1 else '{:,.0f}'.format(value))

    def _pct(self, part, whole):
        if not whole:
            return 0
        return round((part / whole) * 100)

    def _parse_float(self, value, default=0.0):
        if value in (None, False, ''):
            return default
        try:
            return float(str(value).replace(',', '').split()[0])
        except (TypeError, ValueError):
            return default

    def _parse_time_float(self, value, default=10.0):
        if value in (None, False, ''):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if ':' in text:
            parts = text.split(':')
            try:
                return int(parts[0]) + (int(parts[1]) / 60.0)
            except (TypeError, ValueError):
                return default
        return self._parse_float(text, default)

    def _map_category(self, label):
        text = (label or '').lower()
        if 'hazard' in text:
            return 'hazardous'
        if 'wet' in text or 'organic' in text or 'food' in text:
            return 'wet'
        if 'e-waste' in text or 'ewaste' in text or 'electronic' in text:
            return 'ewaste'
        if 'plastic' in text:
            return 'plastic'
        if 'dry' in text or 'recycl' in text or 'paper' in text or 'cardboard' in text:
            return 'dry'
        return 'other'

    def _resolve_vendor(self, vendor_ref, create_name=None):
        Vendor = self.env['wm.vendor']
        if not vendor_ref and not create_name:
            return Vendor.browse()
        if isinstance(vendor_ref, int) or (isinstance(vendor_ref, str) and str(vendor_ref).isdigit()):
            vendor = Vendor.browse(int(vendor_ref))
            return vendor if vendor.exists() else Vendor.browse()
        name = (vendor_ref or create_name or '').strip()
        if not name:
            return Vendor.browse()
        vendor = Vendor.search([('name', 'ilike', name)], limit=1)
        if vendor:
            return vendor
        partner = self.env['res.partner'].create({
            'name': name,
            'supplier_rank': 1,
            'company_type': 'company',
        })
        return Vendor.create({
            'partner_id': partner.id,
            'state': 'active',
            'disposal_capability': True,
            'recycling_capability': True,
        })

    def _resolve_entry(self, entry_ref):
        Entry = self.env['wm.entry']
        if not entry_ref:
            return Entry.browse()
        if isinstance(entry_ref, int) or (isinstance(entry_ref, str) and str(entry_ref).isdigit()):
            return Entry.browse(int(entry_ref))
        return Entry.search([('code', '=', entry_ref)], limit=1)

    def _page(self, records, page=1, page_size=50):
        page = max(1, int(page or 1))
        page_size = min(200, max(1, int(page_size or 50)))
        total = len(records)
        start = (page - 1) * page_size
        end = start + page_size
        return records[start:end], total, page, page_size

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, filters=None):
        Entry = self.env['wm.entry']
        Schedule = self.env['wm.collection.schedule']
        Pickup = self.env['wm.pickup.tracking']
        Recycling = self.env['wm.recycling']
        Disposal = self.env['wm.disposal']
        Vendor = self.env['wm.vendor']
        Compliance = self.env['wm.compliance']
        Segregation = self.env['wm.segregation']
        today = fields.Date.context_today(self)

        entry_domain = [('state', '!=', 'cancelled')]
        total_waste = sum(Entry.search(entry_domain).mapped('quantity'))
        collected = sum(Pickup.search([('state', 'in', ('picked_up', 'delivered', 'completed'))]).mapped('collected_qty')) \
            or sum(Schedule.search([('state', '=', 'completed')]).mapped('quantity'))
        recycled = sum(Recycling.search([('state', '=', 'completed')]).mapped('quantity'))
        disposed = sum(Disposal.search([('state', '=', 'completed')]).mapped('quantity'))
        pending = sum(Entry.search([('state', 'in', ('draft', 'recorded', 'pending_segregation'))]).mapped('quantity'))
        compliance_total = Compliance.search_count([])
        compliance_ok = Compliance.search_count([('state', 'in', ('valid', 'renewed'))])
        compliance_rate = self._pct(compliance_ok, compliance_total) if compliance_total else 100

        # Trend — last 5 weeks
        trend = []
        for i in range(4, -1, -1):
            week_end = today - timedelta(days=i * 7)
            week_start = week_end - timedelta(days=6)
            generated = sum(Entry.search([
                ('entry_datetime', '>=', fields.Datetime.to_datetime(week_start)),
                ('entry_datetime', '<=', fields.Datetime.to_datetime(week_end) + timedelta(days=1)),
                ('state', '!=', 'cancelled'),
            ]).mapped('quantity'))
            week_collected = sum(Schedule.search([
                ('pickup_date', '>=', week_start),
                ('pickup_date', '<=', week_end),
                ('state', '=', 'completed'),
            ]).mapped('quantity'))
            trend.append({
                'day': week_end.strftime('%b %d'),
                'generated': round(generated),
                'collected': round(week_collected),
            })

        # Categories
        cat_totals = defaultdict(float)
        for row in Entry.read_group(entry_domain, ['quantity:sum'], ['waste_category']):
            cat_totals[row['waste_category']] = row['quantity'] or 0.0
        cat_colors = {
            'dry': '#7c3aed',
            'wet': '#16a34a',
            'plastic': '#2563eb',
            'hazardous': '#dc2626',
            'ewaste': '#2563eb',
            'other': '#64748b',
        }
        cat_labels = dict(Entry._fields['waste_category'].selection)
        categories = []
        for key, qty in sorted(cat_totals.items(), key=lambda x: -x[1]):
            categories.append({
                'name': cat_labels.get(key, key or 'Other'),
                'pct': self._pct(qty, total_waste),
                'color': cat_colors.get(key, '#64748b'),
                'qty': qty,
            })

        recent = []
        for entry in Entry.search(entry_domain, limit=5, order='entry_datetime desc'):
            status = 'Pending'
            status_key = 'warn'
            if entry.schedule_ids.filtered(lambda s: s.state == 'completed'):
                status, status_key = 'Collected', 'ok'
            elif entry.hazardous and entry.state == 'pending_segregation':
                status, status_key = 'Critical', 'bad'
            recent.append({
                'id': entry.code,
                'location': entry.location_detail or entry.site or '',
                'category': cat_labels.get(entry.waste_category, entry.waste_category),
                'weight': self._fmt_kg(entry.quantity),
                'status': status,
                'statusKey': status_key,
            })

        alerts = []
        delayed = Schedule.search_count([('state', 'in', ('delayed', 'missed'))])
        if delayed:
            alerts.append({
                'title': 'Missed Pickup',
                'text': '%s collection(s) delayed or missed.' % delayed,
                'when': 'Today',
                'tone': 'danger',
            })
        overdue_comp = Compliance.search_count([('state', '=', 'expired')])
        if overdue_comp:
            alerts.append({
                'title': 'Compliance Overdue',
                'text': '%s compliance item(s) expired.' % overdue_comp,
                'when': 'Today',
                'tone': 'warn',
            })
        completed_seg = Segregation.search_count([
            ('state', '=', 'completed'),
            ('date_end', '>=', fields.Datetime.to_datetime(today)),
        ])
        if completed_seg:
            alerts.append({
                'title': 'Segregation Completed',
                'text': '%s segregation(s) completed today.' % completed_seg,
                'when': 'Today',
                'tone': 'ok',
            })

        upcoming = []
        for sch in Schedule.search([
            ('pickup_date', '>=', today),
            ('state', 'in', ('scheduled', 'confirmed', 'in_progress')),
        ], limit=5, order='pickup_date asc'):
            upcoming.append({
                'name': sch.entry_id.waste_type if sch.entry_id else (sch.name or 'Collection'),
                'when': '%s %s' % (self._wm_date(sch.pickup_date), sch._fmt_window()),
                'vendor': sch.vendor_id.name if sch.vendor_id else '',
            })

        return {
            'kpis': {
                'total_waste': total_waste,
                'collected': collected,
                'recycled': recycled,
                'disposed': disposed,
                'pending': pending,
                'compliance': compliance_rate,
                'pending_collections': Schedule.search_count([('state', 'in', ('draft', 'scheduled', 'confirmed'))]),
                'completed_pickups': Pickup.search_count([('state', 'in', ('picked_up', 'completed', 'delivered'))]),
                'active_vendors': Vendor.search_count([('state', '=', 'active')]),
                'recycling_rate': self._pct(recycled, total_waste),
                'disposal_rate': self._pct(disposed, total_waste),
                'compliance_rate': compliance_rate,
                'overdue_compliance': overdue_comp,
                'upcoming_collections': len(upcoming),
            },
            'kpi_cards': [
                {'label': 'Total Waste', 'value': self._fmt_kg(total_waste), 'hint': '', 'hintClass': 'ok', 'tone': ''},
                {'label': 'Collected', 'value': self._fmt_kg(collected), 'hint': '', 'hintClass': 'ok', 'tone': ''},
                {'label': 'Recycled', 'value': self._fmt_kg(recycled), 'hint': '', 'hintClass': 'ok', 'tone': ''},
                {'label': 'Disposed', 'value': self._fmt_kg(disposed), 'hint': '', 'hintClass': 'warn', 'tone': ''},
                {'label': 'Pending', 'value': self._fmt_kg(pending), 'hint': '', 'hintClass': 'warn', 'tone': 'warn'},
                {'label': 'Compliance', 'value': '%s%%' % compliance_rate, 'hint': '', 'hintClass': 'ok', 'tone': 'ok'},
            ],
            'trend': trend,
            'categories': categories,
            'efficiency': self._pct(collected, total_waste) if total_waste else 0,
            'recent': recent,
            'alerts': alerts,
            'upcoming': upcoming,
            'alertCount': len([a for a in alerts if a.get('tone') in ('danger', 'warn')]),
        }

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------
    @api.model
    def get_entries_data(self, filters=None):
        filters = filters or {}
        Entry = self.env['wm.entry']
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('priority'):
            domain.append(('priority', '=', filters['priority']))
        if filters.get('hazardous'):
            domain.append(('hazardous', '=', True))
        if filters.get('waste_category'):
            domain.append(('waste_category', '=', filters['waste_category']))
        if filters.get('site'):
            domain.append(('site', 'ilike', filters['site']))
        if filters.get('search'):
            q = filters['search']
            domain = expression.AND([domain, ['|', '|', '|',
                ('code', 'ilike', q),
                ('waste_type', 'ilike', q),
                ('site', 'ilike', q),
                ('location_detail', 'ilike', q),
            ]])
        if filters.get('tab') == 'Pending Segregation':
            domain.append(('state', '=', 'pending_segregation'))
        elif filters.get('tab') == 'Pending Collection':
            domain.append(('state', 'in', ('recorded', 'pending_segregation', 'processed')))
        elif filters.get('tab') == 'High Priority':
            domain.append(('priority', '=', 'high'))
        elif filters.get('tab') == 'Hazardous Waste':
            domain.append(('hazardous', '=', True))
        elif filters.get('tab') == 'Recyclable Waste':
            domain.append(('waste_category', 'in', ('dry', 'plastic')))
        elif filters.get('tab') == "Today's Entries":
            today = fields.Date.context_today(self)
            domain.append(('entry_datetime', '>=', fields.Datetime.to_datetime(today)))
            domain.append(('entry_datetime', '<', fields.Datetime.to_datetime(today) + timedelta(days=1)))

        records = Entry.search(domain, order='entry_datetime desc')
        page_recs, total, page, page_size = self._page(records, filters.get('page'), filters.get('page_size'))
        rows = [r.to_api_dict() for r in page_recs]

        total_qty = sum(Entry.search([('state', '!=', 'cancelled')]).mapped('quantity'))
        recycled = sum(self.env['wm.recycling'].search([('state', '=', 'completed')]).mapped('quantity'))
        seg_pending = Entry.search_count([('state', '=', 'pending_segregation')])
        col_pending = self.env['wm.collection.schedule'].search_count([
            ('state', 'in', ('draft', 'scheduled', 'confirmed')),
        ])
        return {
            'kpis': [
                {'label': 'Total Entries', 'value': str(Entry.search_count([])), 'hint': '', 'tone': 'info'},
                {'label': 'Total Quantity', 'value': self._fmt_kg(total_qty), 'hint': '', 'tone': 'info'},
                {'label': 'Segregation Pending', 'value': str(seg_pending), 'hint': '', 'tone': 'warn'},
                {'label': 'Collection Pending', 'value': str(col_pending), 'hint': '', 'tone': 'bad'},
                {'label': 'Recycled', 'value': self._fmt_kg(recycled), 'hint': '', 'tone': 'ok'},
            ],
            'steps': [
                {'label': 'Generated', 'value': str(Entry.search_count([('state', '!=', 'cancelled')])), 'key': 'info'},
                {'label': 'Segregation', 'value': '%s Pending' % seg_pending, 'key': 'warn'},
                {'label': 'Collection', 'value': '%s Pending' % col_pending, 'key': 'bad'},
                {'label': 'Recycling', 'value': 'Active' if recycled else '—', 'key': ''},
            ],
            'rows': rows,
            'total': total,
            'page': page,
            'page_size': page_size,
            'pageInfo': 'Showing %s–%s of %s entries' % (
                ((page - 1) * page_size) + 1 if total else 0,
                min(page * page_size, total),
                total,
            ),
            'activity': self._recent_activity(limit=5),
            'categoryBars': self.get_dashboard_data().get('categories', [])[:4],
        }

    @api.model
    def get_entry_detail(self, entry_id):
        entry = self.env['wm.entry'].browse(int(entry_id))
        if not entry.exists():
            return self._wm_fail('Waste entry not found')
        data = entry.to_api_dict()
        data['segregations'] = [s.to_api_dict() for s in entry.segregation_ids]
        data['schedules'] = [s.to_api_dict() for s in entry.schedule_ids]
        data['recyclings'] = [r.to_api_dict() for r in entry.recycling_ids]
        data['disposals'] = [d.to_api_dict() for d in entry.disposal_ids]
        return self._wm_ok(data)

    @api.model
    def create_entry(self, values=None):
        return self._safe(self._create_entry, values or {})

    def _create_entry(self, values):
        vals = self._entry_vals(values)
        entry = self.env['wm.entry'].create(vals)
        if not values.get('as_draft', True):
            entry.action_confirm()
        return {'id': entry.id, 'code': entry.code, 'row': entry.to_api_dict()}

    @api.model
    def update_entry(self, entry_id, values=None):
        return self._safe(self._update_entry, entry_id, values or {})

    def _update_entry(self, entry_id, values):
        entry = self.env['wm.entry'].browse(int(entry_id))
        if not entry.exists():
            raise UserError('Waste entry not found')
        entry.write(self._entry_vals(values, update=True))
        return {'id': entry.id, 'row': entry.to_api_dict()}

    def _entry_vals(self, values, update=False):
        vals = {}
        mapping = {
            'name': 'name',
            'waste_type': 'waste_type',
            'description': 'description',
            'notes': 'notes',
            'source': 'source',
            'department': 'department',
            'site': 'site',
            'building': 'building',
            'floor': 'floor',
            'location': 'location_detail',
            'location_detail': 'location_detail',
            'priority': 'priority',
            'hazardous': 'hazardous',
            'segregation_required': 'segregation_required',
        }
        for src, dest in mapping.items():
            if src in values:
                vals[dest] = values[src]
        if 'category' in values or 'waste_category' in values:
            vals['waste_category'] = self._map_category(values.get('waste_category') or values.get('category'))
        if 'amount' in values or 'quantity' in values:
            vals['quantity'] = self._parse_float(values.get('quantity', values.get('amount')))
        if 'date' in values or 'time' in values or 'entry_datetime' in values:
            if values.get('entry_datetime'):
                vals['entry_datetime'] = values['entry_datetime']
            else:
                date_s = values.get('date') or fields.Date.to_string(fields.Date.context_today(self))
                time_s = values.get('time') or '09:00'
                vals['entry_datetime'] = '%s %s:00' % (date_s, time_s if len(time_s) == 5 else time_s[:5])
        if 'vendor' in values or 'preferred_vendor_id' in values:
            vendor = self._resolve_vendor(values.get('preferred_vendor_id') or values.get('vendor'))
            if vendor:
                vals['preferred_vendor_id'] = vendor.id
        if 'employee_id' in values:
            vals['employee_id'] = int(values['employee_id']) if values['employee_id'] else False
        if 'location_id' in values:
            vals['location_id'] = int(values['location_id']) if values['location_id'] else False
        if 'product_id' in values:
            vals['product_id'] = int(values['product_id']) if values['product_id'] else False
        if not update and 'quantity' not in vals:
            vals['quantity'] = self._parse_float(values.get('amount'), 1.0) or 1.0
        if not update and 'site' not in vals:
            vals['site'] = self.env['ir.config_parameter'].sudo().get_param(
                'waste_management.default_site', 'Site Alpha'
            )
        if not update and 'waste_type' not in vals:
            vals['waste_type'] = values.get('category') or 'General'
        return vals

    @api.model
    def confirm_entry(self, entry_id):
        return self._safe(lambda: self.env['wm.entry'].browse(int(entry_id)).action_confirm() or True)

    @api.model
    def cancel_entry(self, entry_id):
        return self._safe(lambda: self.env['wm.entry'].browse(int(entry_id)).action_cancel() or True)

    @api.model
    def delete_entry(self, entry_id):
        def _do():
            entry = self.env['wm.entry'].browse(int(entry_id))
            if entry.state not in ('draft', 'cancelled'):
                raise UserError('Only draft or cancelled entries can be deleted.')
            entry.unlink()
            return True
        return self._safe(_do)

    # ------------------------------------------------------------------
    # Segregation
    # ------------------------------------------------------------------
    @api.model
    def get_segregation_data(self, filters=None):
        filters = filters or {}
        Seg = self.env['wm.segregation']
        Entry = self.env['wm.entry']
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('search'):
            q = filters['search']
            domain = expression.AND([domain, ['|', '|',
                ('name', 'ilike', q),
                ('entry_id.code', 'ilike', q),
                ('location', 'ilike', q),
            ]])
        records = Seg.search(domain, order='id desc')
        # Also surface pending entries without segregation yet
        pending_entries = Entry.search([('state', '=', 'pending_segregation')])
        rows = [r.to_api_dict() for r in records]
        for entry in pending_entries:
            if not entry.segregation_ids:
                rows.insert(0, {
                    'id': False,
                    'entry_id': entry.id,
                    'priority': dict(entry._fields['priority'].selection).get(entry.priority, 'Med'),
                    'priorityKey': {'high': 'bad', 'medium': 'warn', 'low': 'info'}.get(entry.priority, 'warn'),
                    'code': entry.code,
                    'datetime': self._wm_datetime(entry.entry_datetime),
                    'site': entry.site or '',
                    'location': entry.location_detail or '',
                    'type': entry.waste_type or '',
                    'category': self._wm_selection_label(entry, 'waste_category'),
                    'qty': '%s %s' % (entry.quantity, entry.uom_id.name or 'kg'),
                    'status': 'Pending',
                    'statusKey': 'warn',
                    'assignee': '',
                    'state': 'pending',
                })
        today = fields.Date.context_today(self)
        pending = Seg.search_count([('state', '=', 'draft')]) + Entry.search_count([
            ('state', '=', 'pending_segregation'),
            ('segregation_ids', '=', False),
        ])
        in_progress = Seg.search_count([('state', '=', 'in_progress')])
        completed_today = Seg.search_count([
            ('state', '=', 'completed'),
            ('date_end', '>=', fields.Datetime.to_datetime(today)),
        ])
        rejected = Seg.search_count([('state', '=', 'rejected')])
        qty_pending = sum(Entry.search([('state', '=', 'pending_segregation')]).mapped('quantity'))
        return {
            'kpis': [
                {'label': 'Pending Segregation', 'value': str(pending), 'badge': 'NEEDS ATTENTION', 'tone': 'warn'},
                {'label': 'In Progress', 'value': str(in_progress), 'badge': 'ACTIVE', 'tone': 'info'},
                {'label': 'Segregated Today', 'value': str(completed_today), 'badge': 'COMPLETED', 'tone': 'ok'},
                {'label': 'Failed / Rejected', 'value': str(rejected), 'badge': 'CRITICAL', 'tone': 'bad'},
                {'label': 'Qty Pending', 'value': self._fmt_kg(qty_pending), 'badge': '', 'tone': ''},
                {'label': 'Avg Processing Time', 'value': '—', 'badge': '', 'tone': ''},
            ],
            'pipeline': [
                {'label': 'Generated', 'value': str(Entry.search_count([('state', '!=', 'cancelled')]))},
                {'label': 'Segregation Pending', 'value': str(pending), 'active': True},
                {'label': 'Segregated', 'value': str(Seg.search_count([('state', '=', 'completed')]))},
                {'label': 'Collection Ready', 'value': str(self.env['wm.collection.schedule'].search_count([]))},
            ],
            'rows': rows,
            'pageInfo': 'Showing %s of %s records' % (len(rows), len(rows)),
        }

    @api.model
    def create_segregation(self, values=None):
        return self._safe(self._create_segregation, values or {})

    def _create_segregation(self, values):
        entry = self._resolve_entry(values.get('entry_id') or values.get('entry_code') or values.get('code'))
        if not entry:
            raise UserError('Waste entry is required for segregation.')
        if entry.state == 'draft':
            entry.action_confirm()
        vals = {
            'entry_id': entry.id,
            'original_qty': self._parse_float(values.get('original_qty'), entry.quantity),
            'dry_qty': self._parse_float(values.get('dry_qty')),
            'wet_qty': self._parse_float(values.get('wet_qty')),
            'hazardous_qty': self._parse_float(values.get('hazardous_qty')),
            'residual_qty': self._parse_float(values.get('residual_qty')),
            'assignee': values.get('assignee') or '',
            'location': values.get('location') or entry.location_detail or '',
            'notes': values.get('notes') or '',
            'method': values.get('method') or '',
        }
        if values.get('employee_id'):
            vals['employee_id'] = int(values['employee_id'])
        seg = self.env['wm.segregation'].create(vals)
        if values.get('start', True):
            seg.action_start()
        return {'id': seg.id, 'row': seg.to_api_dict()}

    @api.model
    def start_segregation(self, segregation_id):
        return self._safe(lambda: self.env['wm.segregation'].browse(int(segregation_id)).action_start() or True)

    @api.model
    def complete_segregation(self, segregation_id, values=None):
        def _do():
            seg = self.env['wm.segregation'].browse(int(segregation_id))
            values = values or {}
            write_vals = {}
            for key in ('dry_qty', 'wet_qty', 'hazardous_qty', 'residual_qty', 'rejected_qty', 'notes'):
                if key in values:
                    write_vals[key] = self._parse_float(values[key]) if key.endswith('qty') else values[key]
            if write_vals:
                seg.write(write_vals)
            seg.action_complete()
            return {'id': seg.id, 'row': seg.to_api_dict()}
        return self._safe(_do)

    # ------------------------------------------------------------------
    # Collection schedule
    # ------------------------------------------------------------------
    @api.model
    def get_schedule_data(self, filters=None):
        filters = filters or {}
        Schedule = self.env['wm.collection.schedule']
        today = fields.Date.context_today(self)
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('search'):
            q = filters['search']
            domain = expression.AND([domain, ['|', '|',
                ('name', 'ilike', q),
                ('site', 'ilike', q),
                ('vendor_id.name', 'ilike', q),
            ]])
        records = Schedule.search(domain, order='pickup_date desc, id desc')
        rows = [r.to_api_dict() for r in records]
        return {
            'kpis': [
                {'label': 'Pending Collection', 'value': Schedule.search_count([('state', 'in', ('draft', 'scheduled'))])},
                {'label': 'Scheduled Today', 'value': Schedule.search_count([('pickup_date', '=', today), ('state', 'in', ('scheduled', 'confirmed'))]), 'tone': 'info'},
                {'label': 'In Progress', 'value': Schedule.search_count([('state', '=', 'in_progress')]), 'tone': 'warn'},
                {'label': 'Completed Today', 'value': Schedule.search_count([('pickup_date', '=', today), ('state', '=', 'completed')]), 'tone': 'ok'},
                {'label': 'Overdue', 'value': Schedule.search_count([('state', 'in', ('delayed', 'missed'))]), 'tone': 'bad'},
            ],
            'pipeline': [
                {'label': 'Segregated', 'value': self.env['wm.segregation'].search_count([('state', '=', 'completed')])},
                {'label': 'Ready', 'value': Schedule.search_count([('state', '=', 'draft')])},
                {'label': 'Scheduled', 'value': Schedule.search_count([('state', '=', 'scheduled')]), 'active': True},
                {'label': 'Pickup', 'value': Schedule.search_count([('state', '=', 'in_progress')])},
                {'label': 'Collected', 'value': Schedule.search_count([('state', '=', 'completed')])},
                {'label': 'Processing', 'value': self.env['wm.recycling'].search_count([('state', 'in', ('confirmed', 'in_progress'))])},
            ],
            'rows': rows,
            'pageInfo': 'Showing %s schedules' % len(rows),
            'ready_entries': [
                {
                    'id': e.id,
                    'code': e.code,
                    'qty': e.quantity,
                    'label': '%s (%s kg)' % (e.code, e.quantity),
                }
                for e in self.env['wm.entry'].search([
                    ('state', 'in', ('processed', 'pending_segregation', 'recorded')),
                ], limit=20)
            ],
        }

    @api.model
    def create_schedule(self, values=None):
        return self._safe(self._create_schedule, values or {})

    def _create_schedule(self, values):
        entry_refs = values.get('entry_ids') or values.get('selected') or []
        if values.get('entry_id') or values.get('entry'):
            entry_refs = list(entry_refs) + [values.get('entry_id') or values.get('entry')]
        entries = self.env['wm.entry']
        for ref in entry_refs:
            entry = self._resolve_entry(ref)
            if entry:
                entries |= entry
        vendor = self._resolve_vendor(values.get('vendor_id') or values.get('vendor'), create_name=values.get('vendor'))
        qty = self._parse_float(values.get('quantity'))
        if not qty and entries:
            qty = sum(entries.mapped('quantity'))
        vals = {
            'entry_id': entries[:1].id if entries else False,
            'entry_ids': [(6, 0, entries.ids)] if entries else False,
            'quantity': qty or 1.0,
            'pickup_date': values.get('date') or values.get('pickup_date') or fields.Date.context_today(self),
            'time_from': self._parse_time_float(values.get('time_from'), 10.0),
            'time_to': self._parse_time_float(values.get('time_to'), 11.0),
            'site': values.get('site') or (entries[:1].site if entries else 'Main Facility'),
            'priority': (values.get('priority') or 'medium').lower() if isinstance(values.get('priority'), str) else (values.get('priority') or 'medium'),
            'notes': values.get('notes') or '',
            'destination': values.get('destination') or '',
        }
        if vals['priority'] not in ('low', 'medium', 'high'):
            vals['priority'] = {'High': 'high', 'Med': 'medium', 'Low': 'low'}.get(values.get('priority'), 'medium')
        if vendor:
            vals['vendor_id'] = vendor.id
        if values.get('vehicle_id'):
            vals['vehicle_id'] = int(values['vehicle_id'])
        if values.get('driver_id'):
            vals['driver_id'] = int(values['driver_id'])
        schedule = self.env['wm.collection.schedule'].create(vals)
        if values.get('confirm', True):
            schedule.action_schedule()
        return {'id': schedule.id, 'row': schedule.to_api_dict()}

    @api.model
    def confirm_schedule(self, schedule_id):
        return self._safe(lambda: self.env['wm.collection.schedule'].browse(int(schedule_id)).action_confirm() or True)

    @api.model
    def cancel_schedule(self, schedule_id):
        return self._safe(lambda: self.env['wm.collection.schedule'].browse(int(schedule_id)).action_cancel() or True)

    @api.model
    def start_schedule(self, schedule_id):
        return self._safe(lambda: self.env['wm.collection.schedule'].browse(int(schedule_id)).action_start() or True)

    @api.model
    def complete_schedule(self, schedule_id):
        return self._safe(lambda: self.env['wm.collection.schedule'].browse(int(schedule_id)).action_complete() or True)

    # ------------------------------------------------------------------
    # Pickup
    # ------------------------------------------------------------------
    @api.model
    def get_pickup_data(self, filters=None):
        filters = filters or {}
        Pickup = self.env['wm.pickup.tracking']
        today = fields.Date.context_today(self)
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('search'):
            q = filters['search']
            domain = expression.AND([domain, ['|', '|',
                ('name', 'ilike', q),
                ('site', 'ilike', q),
                ('vendor_id.name', 'ilike', q),
            ]])
        records = Pickup.search(domain, order='planned_date desc, id desc')
        return {
            'kpis': [
                {'label': 'En Route', 'value': Pickup.search_count([('state', '=', 'en_route')]), 'tone': 'info'},
                {'label': 'Arrived', 'value': Pickup.search_count([('state', '=', 'arrived')]), 'tone': 'warn'},
                {'label': 'Collected Today', 'value': Pickup.search_count([
                    ('state', 'in', ('picked_up', 'completed', 'delivered')),
                    ('actual_date', '>=', fields.Datetime.to_datetime(today)),
                ]), 'tone': 'ok'},
                {'label': 'Delayed', 'value': Pickup.search_count([('state', '=', 'delayed')]), 'tone': 'bad'},
                {'label': 'Exceptions', 'value': Pickup.search_count([('state', '=', 'exception')]), 'tone': 'bad'},
            ],
            'rows': [r.to_api_dict() for r in records],
        }

    @api.model
    def get_pickup_detail(self, pickup_id):
        pickup = self.env['wm.pickup.tracking'].browse(int(pickup_id))
        if not pickup.exists():
            return self._wm_fail('Pickup not found')
        return self._wm_ok(pickup.to_api_dict())

    @api.model
    def update_pickup_status(self, pickup_id, action=None, values=None):
        def _do():
            pickup = self.env['wm.pickup.tracking'].browse(int(pickup_id))
            if not pickup.exists():
                raise UserError('Pickup not found')
            values = values or {}
            act = (action or values.get('action') or '').lower()
            if act in ('start', 'en_route'):
                pickup.action_start()
            elif act in ('arrive', 'arrived'):
                pickup.action_arrive()
            elif act in ('collect', 'picked_up'):
                pickup.action_collect(values.get('collected_qty') or values.get('quantity'))
            elif act in ('complete', 'completed'):
                pickup.action_complete()
            elif act in ('delay', 'delayed'):
                pickup.action_delay()
            else:
                raise UserError('Unknown pickup action: %s' % action)
            return {'id': pickup.id, 'row': pickup.to_api_dict()}
        return self._safe(_do)

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------
    @api.model
    def get_vendors_data(self, filters=None):
        filters = filters or {}
        Vendor = self.env['wm.vendor']
        domain = []
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('search'):
            q = filters['search']
            domain = expression.AND([domain, ['|', '|',
                ('name', 'ilike', q),
                ('code', 'ilike', q),
                ('phone', 'ilike', q),
            ]])
        records = Vendor.search(domain)
        return {
            'kpis': [
                {'label': 'Total Vendors', 'value': Vendor.search_count([])},
                {'label': 'Active', 'value': Vendor.search_count([('state', '=', 'active')]), 'tone': 'ok'},
                {'label': 'Expiring Contracts', 'value': Vendor.search_count([('state', '=', 'expiring')]), 'tone': 'warn'},
                {'label': 'Suspended', 'value': Vendor.search_count([('state', '=', 'suspended')]), 'tone': 'bad'},
            ],
            'rows': [r.to_api_dict() for r in records],
        }

    @api.model
    def get_vendor_detail(self, vendor_id):
        vendor = self.env['wm.vendor'].browse(int(vendor_id))
        if not vendor.exists():
            return self._wm_fail('Vendor not found')
        data = vendor.to_api_dict()
        data.update({
            'eligible': 'ELIGIBLE' if vendor.state == 'active' else 'REVIEW',
            'reviews': '',
            'sites': [vendor.partner_id.city] if vendor.partner_id.city else [],
            'categories': (vendor.waste_categories or '').split(',') if vendor.waste_categories else [],
            'checks': [
                'Contract Active' if vendor.state == 'active' else 'Contract Review',
                'Compliance Valid' if not vendor.license_expiry or vendor.license_expiry >= fields.Date.context_today(self) else 'License Expiring',
                'Required Documents',
                'Waste Category Supported',
                'Service Area Supported',
            ],
            'contract': {
                'code': vendor.code,
                'start': self._wm_date(vendor.contract_start),
                'end': self._wm_date(vendor.contract_end),
                'remaining': '',
            },
            'registration': vendor.license_number or '',
            'since': self._wm_date(vendor.contract_start),
        })
        return self._wm_ok(data)

    @api.model
    def create_vendor(self, values=None):
        return self._safe(self._create_vendor, values or {})

    def _create_vendor(self, values):
        Partner = self.env['res.partner']
        partner = False
        if values.get('partner_id'):
            partner = Partner.browse(int(values['partner_id']))
        else:
            partner = Partner.create({
                'name': values.get('name') or values.get('contact') or 'Waste Vendor',
                'phone': values.get('phone'),
                'email': values.get('email'),
                'city': values.get('sites') or values.get('city'),
                'supplier_rank': 1,
                'company_type': 'company',
            })
        vendor = self.env['wm.vendor'].create({
            'partner_id': partner.id,
            'waste_categories': values.get('services') or values.get('waste_categories') or '',
            'vendor_type': values.get('vendor_type') or 'mixed',
            'recycling_capability': bool(values.get('recycling_capability')),
            'disposal_capability': bool(values.get('disposal_capability')),
            'license_number': values.get('license_number') or '',
            'license_expiry': values.get('license_expiry') or False,
            'contract_start': values.get('contract_start') or False,
            'contract_end': values.get('contract_end') or False,
            'notes': values.get('notes') or '',
            'state': 'active',
        })
        # Prefer contact person as related contact note if provided
        if values.get('contact') and values.get('contact') != partner.name:
            partner.comment = (partner.comment or '') + '\nContact: %s' % values['contact']
        return {'id': vendor.id, 'row': vendor.to_api_dict()}

    @api.model
    def update_vendor(self, vendor_id, values=None):
        def _do():
            vendor = self.env['wm.vendor'].browse(int(vendor_id))
            if not vendor.exists():
                raise UserError('Vendor not found')
            values = values or {}
            partner_vals = {}
            if values.get('name'):
                partner_vals['name'] = values['name']
            if 'phone' in values:
                partner_vals['phone'] = values['phone']
            if 'email' in values:
                partner_vals['email'] = values['email']
            if partner_vals:
                vendor.partner_id.write(partner_vals)
            write_vals = {}
            for key in ('waste_categories', 'vendor_type', 'recycling_capability', 'disposal_capability',
                        'license_number', 'license_expiry', 'contract_start', 'contract_end', 'notes', 'rating', 'state'):
                if key in values:
                    write_vals[key] = values[key]
            if 'services' in values:
                write_vals['waste_categories'] = values['services']
            if write_vals:
                vendor.write(write_vals)
            return {'id': vendor.id, 'row': vendor.to_api_dict()}
        return self._safe(_do)

    # ------------------------------------------------------------------
    # Recycling / Disposal / Compliance
    # ------------------------------------------------------------------
    @api.model
    def get_recycling_data(self, filters=None):
        Rec = self.env['wm.recycling']
        records = Rec.search([], order='recycling_date desc, id desc')
        completed_qty = sum(Rec.search([('state', '=', 'completed')]).mapped('quantity'))
        return {
            'kpis': [
                {'label': 'Pending', 'value': Rec.search_count([('state', '=', 'draft')]), 'tone': 'warn'},
                {'label': 'Processing', 'value': Rec.search_count([('state', 'in', ('confirmed', 'in_progress'))]), 'tone': 'info'},
                {'label': 'Completed YTD', 'value': self._fmt_kg(completed_qty), 'tone': 'ok'},
                {'label': 'Rejected', 'value': Rec.search_count([('state', '=', 'cancelled')]), 'tone': 'bad'},
            ],
            'rows': [r.to_api_dict() for r in records],
        }

    @api.model
    def create_recycling(self, values=None):
        return self._safe(self._create_recycling, values or {})

    def _create_recycling(self, values):
        entry = self._resolve_entry(values.get('source') or values.get('entry_id') or values.get('entry'))
        vendor = self._resolve_vendor(values.get('vendor_id') or values.get('vendor'), create_name=values.get('vendor'))
        rec = self.env['wm.recycling'].create({
            'entry_id': entry.id if entry else False,
            'material': values.get('type') or values.get('material') or '',
            'quantity': self._parse_float(values.get('received') or values.get('quantity'), 1.0),
            'method': values.get('method') or '',
            'vendor_id': vendor.id if vendor else False,
            'notes': values.get('notes') or '',
            'recycling_date': values.get('date') or fields.Date.context_today(self),
        })
        if vendor:
            vendor.recycling_capability = True
        return {'id': rec.id, 'row': rec.to_api_dict()}

    @api.model
    def complete_recycling(self, recycling_id):
        def _do():
            rec = self.env['wm.recycling'].browse(int(recycling_id))
            if rec.state == 'draft':
                rec.action_confirm()
            rec.action_complete()
            return {'id': rec.id, 'row': rec.to_api_dict()}
        return self._safe(_do)

    @api.model
    def get_disposal_data(self, filters=None):
        Disp = self.env['wm.disposal']
        records = Disp.search([], order='disposal_date desc, id desc')
        return {
            'kpis': [
                {'label': 'Pending Approval', 'value': Disp.search_count([('state', '=', 'draft')]), 'tone': 'warn'},
                {'label': 'Scheduled', 'value': Disp.search_count([('state', '=', 'confirmed')]), 'tone': 'info'},
                {'label': 'Completed', 'value': Disp.search_count([('state', '=', 'completed')]), 'tone': 'ok'},
                {'label': 'Rejected', 'value': Disp.search_count([('state', '=', 'cancelled')]), 'tone': 'bad'},
            ],
            'rows': [r.to_api_dict() for r in records],
        }

    @api.model
    def create_disposal(self, values=None):
        return self._safe(self._create_disposal, values or {})

    def _create_disposal(self, values):
        source_ref = values.get('source') or values.get('entry_id') or values.get('entry')
        entry = self._resolve_entry(source_ref)
        vendor = self._resolve_vendor(values.get('vendor_id') or values.get('vendor'), create_name=values.get('vendor'))
        method_map = {
            'landfill': 'landfill',
            'incineration': 'incineration',
            'chemical': 'chemical',
            'chemical treatment': 'chemical',
            'authorized disposal': 'other',
            'other': 'other',
        }
        method = method_map.get((values.get('method') or 'landfill').lower(), 'other')
        notes = values.get('notes') or ''
        # Allow free-text source when it is not an existing waste entry code
        if source_ref and not entry:
            notes = (('Source: %s' % source_ref) + ('\n' + notes if notes else '')).strip()
        disp = self.env['wm.disposal'].create({
            'entry_id': entry.id if entry else False,
            'material': values.get('type') or values.get('material') or '',
            'quantity': self._parse_float(values.get('qty') or values.get('quantity'), 1.0),
            'method': method,
            'vendor_id': vendor.id if vendor else False,
            'notes': notes,
            'certificate_ref': values.get('certificate_ref') or (str(values.get('cost')) if values.get('cost') not in (None, False, '') else ''),
            'disposal_date': values.get('date') or fields.Date.context_today(self),
        })
        if vendor and not vendor.disposal_capability:
            vendor.disposal_capability = True
        data = disp.to_api_dict()
        if source_ref and not entry:
            data['source'] = str(source_ref)
        return {'id': disp.id, 'row': data}

    @api.model
    def complete_disposal(self, disposal_id, values=None):
        def _do():
            disp = self.env['wm.disposal'].browse(int(disposal_id))
            values = values or {}
            if values.get('certificate_ref'):
                disp.certificate_ref = values['certificate_ref']
            if disp.state == 'draft':
                disp.action_confirm()
            if not disp.certificate_ref:
                disp.certificate_ref = 'AUTO-%s' % disp.name
            disp.action_complete()
            return {'id': disp.id, 'row': disp.to_api_dict()}
        return self._safe(_do)

    @api.model
    def get_compliance_data(self, filters=None):
        Comp = self.env['wm.compliance']
        records = Comp.search([], order='expiry_date asc, id desc')
        return {
            'kpis': [
                {'label': 'Compliant', 'value': Comp.search_count([('state', '=', 'valid')]), 'tone': 'ok'},
                {'label': 'Expiring Soon', 'value': Comp.search_count([('state', '=', 'expiring')]), 'tone': 'warn'},
                {'label': 'Expired', 'value': Comp.search_count([('state', '=', 'expired')]), 'tone': 'bad'},
                {'label': 'Renewal In Progress', 'value': Comp.search_count([('state', '=', 'renewed')]), 'tone': 'info'},
            ],
            'rows': [r.to_api_dict() for r in records],
        }

    @api.model
    def create_compliance(self, values=None):
        return self._safe(self._create_compliance, values or {})

    def _create_compliance(self, values):
        comp = self.env['wm.compliance'].create({
            'title': values.get('name') or values.get('title') or 'Compliance Item',
            'regulation': values.get('authority') or values.get('regulation') or '',
            'category': values.get('category') or 'permit',
            'expiry_date': values.get('expiry') or values.get('expiry_date') or False,
            'issue_date': values.get('issue_date') or fields.Date.context_today(self),
            'notes': values.get('notes') or '',
            'state': 'valid',
        })
        return {'id': comp.id, 'row': comp.to_api_dict()}

    @api.model
    def update_compliance(self, compliance_id, values=None):
        def _do():
            comp = self.env['wm.compliance'].browse(int(compliance_id))
            if not comp.exists():
                raise UserError('Compliance record not found')
            values = values or {}
            write_vals = {}
            if values.get('name') or values.get('title'):
                write_vals['title'] = values.get('name') or values.get('title')
            if 'authority' in values or 'regulation' in values:
                write_vals['regulation'] = values.get('authority') or values.get('regulation')
            if 'expiry' in values or 'expiry_date' in values:
                write_vals['expiry_date'] = values.get('expiry') or values.get('expiry_date')
            if 'notes' in values:
                write_vals['notes'] = values['notes']
            if write_vals:
                comp.write(write_vals)
            return {'id': comp.id, 'row': comp.to_api_dict()}
        return self._safe(_do)

    # ------------------------------------------------------------------
    # Analytics / Audit / Settings helpers
    # ------------------------------------------------------------------
    @api.model
    def get_analytics_data(self, filters=None):
        dash = self.get_dashboard_data(filters)
        k = dash['kpis']
        return {
            'kpis': [
                {'label': 'Generation (MTD)', 'value': self._fmt_kg(k.get('total_waste', 0)).replace(' kg', ' t') if k.get('total_waste', 0) >= 1000 else self._fmt_kg(k.get('total_waste', 0))},
                {'label': 'Collection Rate', 'value': '%s%%' % self._pct(k.get('collected', 0), k.get('total_waste', 0) or 1), 'tone': 'ok'},
                {'label': 'Recycling Rate', 'value': '%s%%' % k.get('recycling_rate', 0), 'tone': 'ok'},
                {'label': 'Disposal Rate', 'value': '%s%%' % k.get('disposal_rate', 0), 'tone': 'warn'},
            ],
            'reports': [
                {'name': 'Waste Summary Report', 'category': 'Operations', 'format': 'PDF / Excel', 'key': 'summary'},
                {'name': 'Waste Generation Trend', 'category': 'Analytics', 'format': 'PDF', 'key': 'trend'},
                {'name': 'Collection Performance', 'category': 'Operations', 'format': 'Excel', 'key': 'collection'},
                {'name': 'Delayed/Missed Collection', 'category': 'Exceptions', 'format': 'PDF', 'key': 'delayed'},
                {'name': 'Recycling Performance', 'category': 'Recycling', 'format': 'Excel', 'key': 'recycling'},
                {'name': 'Disposal Summary', 'category': 'Disposal', 'format': 'PDF', 'key': 'disposal'},
                {'name': 'Vendor Performance', 'category': 'Vendors', 'format': 'Excel', 'key': 'vendors'},
                {'name': 'Compliance Expiry/Renewal', 'category': 'Compliance', 'format': 'PDF', 'key': 'compliance'},
                {'name': 'Waste Management Cost', 'category': 'Finance', 'format': 'Excel', 'key': 'cost'},
                {'name': 'Audit & Activity Report', 'category': 'Audit', 'format': 'CSV', 'key': 'audit'},
            ],
            'by_category': dash.get('categories', []),
            'trend': dash.get('trend', []),
            'vendor_performance': [
                {
                    'vendor': v.name,
                    'collections': self.env['wm.collection.schedule'].search_count([('vendor_id', '=', v.id)]),
                    'completed': self.env['wm.collection.schedule'].search_count([
                        ('vendor_id', '=', v.id), ('state', '=', 'completed'),
                    ]),
                    'rating': v.rating,
                }
                for v in self.env['wm.vendor'].search([('state', '=', 'active')], limit=10)
            ],
        }

    @api.model
    def get_report_data(self, report_key=None, filters=None):
        filters = filters or {}
        key = report_key or filters.get('key') or 'summary'
        if key == 'trend':
            return self._wm_ok({'trend': self.get_dashboard_data().get('trend', [])})
        if key == 'collection':
            return self._wm_ok(self.get_schedule_data(filters))
        if key == 'recycling':
            return self._wm_ok(self.get_recycling_data(filters))
        if key == 'disposal':
            return self._wm_ok(self.get_disposal_data(filters))
        if key == 'vendors':
            return self._wm_ok(self.get_vendors_data(filters))
        if key == 'compliance':
            return self._wm_ok(self.get_compliance_data(filters))
        if key == 'audit':
            return self._wm_ok(self.get_audit_data(filters))
        if key == 'delayed':
            return self._wm_ok(self.get_schedule_data({'state': 'delayed'}))
        return self._wm_ok(self.get_analytics_data(filters))

    def _recent_activity(self, limit=10):
        Audit = self.env['wm.audit']
        rows = []
        for a in Audit.search([], limit=limit):
            rows.append({
                'time': self._wm_datetime(a.event_datetime)[11:16] if a.event_datetime else '',
                'text': a.notes or a.action,
                'tone': 'ok' if 'complet' in (a.action or '') else ('info' if 'schedul' in (a.action or '') else ''),
            })
        return rows

    @api.model
    def get_audit_data(self, filters=None):
        filters = filters or {}
        Audit = self.env['wm.audit']
        domain = []
        if filters.get('search'):
            q = filters['search']
            domain = expression.AND([domain, ['|', '|',
                ('action', 'ilike', q),
                ('res_name', 'ilike', q),
                ('notes', 'ilike', q),
            ]])
        today = fields.Date.context_today(self)
        records = Audit.search(domain, order='event_datetime desc', limit=200)
        module_map = {
            'wm.entry': 'Waste Entries',
            'wm.segregation': 'Segregation',
            'wm.collection.schedule': 'Collection',
            'wm.pickup.tracking': 'Pickup',
            'wm.vendor': 'Vendors',
            'wm.recycling': 'Recycling',
            'wm.disposal': 'Disposal',
            'wm.compliance': 'Compliance',
        }
        rows = []
        for a in records:
            rows.append({
                'when': self._wm_datetime(a.event_datetime),
                'user': a.user_id.name if a.user_id else '',
                'module': module_map.get(a.res_model, a.res_model or ''),
                'activity': a.notes or a.action,
                'record': a.res_name or a.name,
                'status': 'Completed',
                'statusKey': 'ok',
            })
        return {
            'kpis': [
                {'label': 'Total Activities', 'value': str(Audit.search_count([]))},
                {'label': 'Today', 'value': Audit.search_count([
                    ('event_datetime', '>=', fields.Datetime.to_datetime(today)),
                ])},
                {'label': 'Approvals', 'value': Audit.search_count([('action', 'ilike', 'confirm')]), 'tone': 'info'},
                {'label': 'Critical Events', 'value': Audit.search_count([
                    ('action', 'in', ('disposal_completed', 'compliance_expired', 'pickup_delayed')),
                ]), 'tone': 'bad'},
            ],
            'rows': rows,
        }

    @api.model
    def get_settings_data(self):
        return self.env['wm.config'].get_settings()

    @api.model
    def save_settings(self, values=None):
        return self.env['wm.config'].save_settings(values or {})

    @api.model
    def get_bootstrap(self):
        """One-shot payload for OWL app initial load."""
        return {
            'dashboard': self.get_dashboard_data(),
            'entries': self.get_entries_data(),
            'segregation': self.get_segregation_data(),
            'schedule': self.get_schedule_data(),
            'pickup': self.get_pickup_data(),
            'vendors': self.get_vendors_data(),
            'recycling': self.get_recycling_data(),
            'disposal': self.get_disposal_data(),
            'compliance': self.get_compliance_data(),
            'analytics': self.get_analytics_data(),
            'audit': self.get_audit_data(),
            'settings': (self.get_settings_data() or {}).get('data') or {},
        }
