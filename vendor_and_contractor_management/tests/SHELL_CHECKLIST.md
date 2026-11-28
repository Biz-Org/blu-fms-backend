# Vendor & Contractor — Odoo Shell Checklist

Run after module upgrade:

```powershell
cd D:\offcie_bizlem\housekepping_management\blu-odoo-sourcecode
python odoo-bin shell -c odoo.conf -d FMS --no-http
```

```python
Dash = env['vc.dashboard']
Vendor = env['vc.vendor']
site = env['vc.site'].create({'name': 'Shell Site'})
v = Vendor.create({'name': 'Shell Vendor', 'contact_person': 'A', 'site_id': site.id})
v.action_submit(); v.action_verify(); v.action_approve()
assert v.state == 'approved'
print('dashboard', Dash.get_dashboard_data()['kpis'])
print('vendors', len(Dash.get_vendors_data()['rows']))
print('reports', Dash.get_report_catalog())
print('OK')
```

Automated tests:

```powershell
python odoo-bin -c odoo.conf -d FMS_TEST --test-enable --stop-after-init -i vendor_and_contractor_management --test-tags=vendor_contractor
```
