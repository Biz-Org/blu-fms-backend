# Asset Management — Phase 7 Validation & Release

Use this checklist before promoting `fms_asset_management` to staging/production.

## Automated gate (required)

From the Odoo source tree:

```bash
cd /Users/palakboricha/Documents/odoo
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/opt/libpq/lib:/opt/homebrew/opt/openssl@3/lib"

.venv/bin/python odoo-bin \
  --addons-path="/Users/palakboricha/Documents/odoo/odoo/addons,/Users/palakboricha/Documents/odoo/addons,/Users/palakboricha/Desktop/asset_management" \
  -d fms_asset_only \
  -u fms_asset_management \
  --test-enable \
  --test-tags /fms_asset_management \
  --stop-after-init \
  --db_host=127.0.0.1 --db_port=5432 \
  --data-dir="/Users/palakboricha/fmss/.odoo-data-18"
```

All tests must pass with **0 failed, 0 errors**.

### In-database release validator

After install/upgrade, administrators can run:

```python
env["fms.asset.validation"].run_release_checks()
```

Every check in the result must have `ok=True`.

## Integration matrix

| Integration | Contract | Validated by |
| --- | --- | --- |
| **Maintenance** | `maintenance.equipment` extended with FMS fields | `test_maintenance_bridge`, lifecycle test |
| **Maintenance requests** | `maintenance.request.equipment_id`; block if disposed | `test_phase4`, lifecycle test |
| **Mail** | Chatter on assignment, transfer, disposal, warranty, schedules | Manual + model `_inherit` |
| **Accounting (optional)** | No hard dependency; `fms.asset.accounting.config` + GL on depreciation post | Phase 5 tests + validator |
| **FMS co-install** | Independent addon path; no edits to other FMS modules | Separate `--addons-path` install |

## Manual smoke (OWL UI)

1. **Dashboard** — KPIs load; recent assets list opens detail.
2. **Global search** — Top bar Enter routes to register with filter.
3. **Register** — Pagination, lifecycle filter, open detail.
4. **Register Asset** — Multi-step wizard creates active asset with Asset ID.
5. **Detail** — Assignment, inspection, transfer/disposal, financial/depreciation.
6. **Operations** — Manager approves transfer and disposal.
7. **QR** — Token resolves to correct asset.
8. **Configuration** — Classification, location, depreciation schedules, accounting bridge.
9. **Maintenance app** — Standard equipment form shows FMS tabs; disposed asset blocks new request.
10. **Report** — Print **FMS Asset Label** on equipment.

## Versioning

Release version follows manifest `18.0.x.0.0` (phase-aligned). Current: see `__manifest__.py`.

## Rollback

- Uninstall removes FMS models; **maintenance.equipment** rows remain (Odoo Maintenance data).
- Disposed assets keep `fms_lifecycle_state=disposed`; archive via standard Maintenance if needed.