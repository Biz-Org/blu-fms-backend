# FMS Helpdesk — Installation & Upgrade

Module path: `custom_addons/fms_helpdesk`  
Current version: **18.0.1.12.0**  
Depends: `base`, `mail`, `resource` (Odoo 18 Community)

## Prerequisites

1. Odoo 18 Community with Python venv activated.
2. `custom_addons` on `addons_path` in `odoo.conf`.
3. Database available (this project uses `odoo_dev` on Postgres).
4. Stop the running Odoo process before `-u` / `--test-enable` if it holds the same database.

## Fresh install

```powershell
cd c:\Users\Priyanka\Downloads\Bizlem\odoo18
.\venv\Scripts\activate
python odoo-bin -c odoo.conf -i fms_helpdesk --stop-after-init
python odoo-bin -c odoo.conf
```

Then in Apps: search **FMS Helpdesk** (or open menu **Helpdesk** after install).

Assign users to groups:

| Group | Typical use |
|---|---|
| Helpdesk Resident | Create/track own tickets, feedback |
| Helpdesk Agent | Work tickets, add resolutions |
| Helpdesk Team Lead | Assign, escalate, verify, close, reopen |
| Helpdesk Manager | Operational oversight |
| Helpdesk Administrator | Categories, routing, SLA, settings |
| Helpdesk Viewer / Management | Read reports and tickets |

## Upgrade existing database

```powershell
cd c:\Users\Priyanka\Downloads\Bizlem\odoo18
.\venv\Scripts\activate
# stop any process using odoo_dev first
python odoo-bin -c odoo.conf -u fms_helpdesk --stop-after-init
python odoo-bin -c odoo.conf
```

After upgrade: hard-refresh the browser (Ctrl+F5) so OWL/SCSS assets reload.

## Run automated tests

```powershell
python odoo-bin -c odoo.conf -u fms_helpdesk --stop-after-init --test-enable --test-tags=fms_helpdesk --log-level=test
```

Look for: `0 failed, 0 error(s)` in the log.

Test packages:

- `test_fms_helpdesk_models` — lifecycle, routing, SLA, escalation, reopen, feedback
- `test_fms_helpdesk_security` — RBAC
- `test_fms_helpdesk_ui` — OWL UI RPC screens (live data)
- `test_fms_helpdesk_api` — Mobile HTTP API
- `test_fms_helpdesk_analytics` — SLA warn/breach + dashboard/report KPIs vs DB

## Mobile API (optional)

See `Document/Helpdesk_API.md`. Clients authenticate with an Odoo session, then call `/fms/helpdesk/api/v1/*`.

## Cron

`Helpdesk: Update SLA Status` runs every 5 minutes (`data/ir_cron_data.xml`). Confirm it is active under Settings → Technical → Automation → Scheduled Actions.

## Notes

- Master priorities/escalation levels ship in `data/fms_helpdesk_master_data.xml`.
- Boolean settings that are missing from `ir.config_parameter` are treated as **off**.
- Cross-module Maintenance / Vendor / Inventory integrations are intentionally ORM-only (no HTTP bridge yet).
