# Asset Management — Phase 2 Foundation Architecture

Standalone Odoo 18 addon (`fms_asset_management`) for FMS module #13.

## Purpose

Extend Odoo **Maintenance equipment** as the canonical operational asset record and provide
FMS-owned **classification**, **facility locations**, **lifecycle fields**, and OWL UI
foundation aligned with Fire & Safety, Compliance, and Reports modules.

## Dependencies

- `maintenance` (canonical `maintenance.equipment`)
- `mail` (chatter / activities on equipment)
- Optional future: `barcodes` (QR/barcode UX in Phase 4)

No dependency on unfinished FMS modules (`fms_core`, Preventive Maintenance, Property #2).

## Canonical asset record

| Concern | Owner |
| --- | --- |
| Operational asset master | `maintenance.equipment` (`_inherit` in this addon) |
| FMS Asset ID | `fms_asset_code` (`ir.sequence` code `fms.asset.code`) |
| FMS classification | `fms.asset.classification` (primary hierarchy) |
| Facility location | `fms.asset.location` (primary hierarchy) |
| Odoo maintenance category | `maintenance.equipment.category` via **optional** `maintenance_category_id` on classification |

Disposal sets `fms_lifecycle_state = disposed` only. **`active` is not cleared automatically**;
archiving remains a separate authorised action. Disposed assets set `fms_operations_locked` and
block master-data writes (location, classification, owner) until Phase 4 workflows expand rules.

## Asset type coverage (`maintenance.equipment`)

| FMS asset family | Supported via | Notes |
| --- | --- | --- |
| HVAC, electrical, mechanical | Name, model, manufacturer, classification, location | Full fit |
| IT assets | Serial, classification, custody (`owner_user_id`) | Full fit |
| Furniture / fixtures | Classification + location; serial optional | Serial defaults to Asset ID when blank |
| Infrastructure | Property/building/room location tree | Full fit |
| Safety equipment | Same canonical record | **Distinct** from `fire.safety.equipment` (domain-specific) |

### Known limitations (documented, not blocking Phase 2)

1. **Serial uniqueness** — Odoo Maintenance enforces unique `serial_no`. Assets without factory
   serials use **`fms_asset_code` as serial** on create to avoid empty-string collisions.
2. **Flat maintenance category** — Odoo `maintenance.equipment.category` is not hierarchical;
   FMS uses `fms.asset.classification` (category → type → sub-type) as master data.
3. **No depreciation engine in Phase 2** — financial fields are stored only; schedules in Phase 5.
4. **Assignment / transfer / warranty** — models deferred to Phases 3–4; `fms.asset.assignment.history`
   and `fms.asset.lifecycle.event` remain separate by design.

## Location strategy

Hierarchy (source of truth: `fms.asset.location`):

`Property → Building → Floor → Wing/Area → Room/Location`

The standard Odoo Maintenance `location` Char field is **mirrored** from the FMS location
`complete_name` for compatibility with the Maintenance app and legacy screens.

`fms_core_location_ref` is reserved for a future bridge to `fms_core.fms.location` (Property #2).

## Model ownership (Phase 2)

| Model | Role |
| --- | --- |
| `maintenance.equipment` (inherit) | Canonical asset + FMS lifecycle/financial/health fields |
| `fms.asset.classification` | Hierarchical classification + optional maintenance category map |
| `fms.asset.location` | Facility location tree |
| `fms.asset.dashboard` | Abstract dashboard counts (live ORM data) |

## RBAC groups

Independent FMS roles (parallel checkboxes, Odoo 18 style):

- `group_asset_administrator`
- `group_asset_manager`
- `group_asset_facility_manager`
- `group_asset_technician`
- `group_asset_finance`
- `group_asset_auditor`

Record rules enforce multi-company boundaries on classification, location, and equipment
for FMS asset groups.

## Frontend (OWL)

- Client actions: `action_dashboard`, `action_register`
- Purple token SCSS (`--am-color-primary: #6d28d9`) consistent with other FMS modules
- Dashboard KPIs call `fms.asset.dashboard.get_dashboard_data()` (no hardcoded stats)

## Future integration contracts (not implemented)

| Module | Contract |
| --- | --- |
| Preventive Maintenance | `equipment_id` → `maintenance.equipment` |
| Maintenance requests | Existing `maintenance.request.equipment_id` |
| Property #2 / `fms_core` | Retarget `fms.asset.location` / `fms_property_integration_ref` |
| Accounting / depreciation | Phase 5 bridge; no custom engine in Phase 2 |
| `fire.safety.equipment` | Optional cross-link field in future addon |
| Reports & Analytics (#25) | Register data sources for equipment + lifecycle fields |

## Phase boundary

**Phase 2 (done):** module scaffold, equipment extension, classification, location,
security, sequences, XML + OWL foundation.

**Phase 3 (done):** multi-step OWL registration, searchable register with pagination,
asset details tabs, `fms.asset.assignment` + `fms.asset.assignment.history` (separate),
`fms.asset.lifecycle.event` timeline, purchase/financial fields on equipment.

**Phase 4 (done, v18.0.3.0.0):** QR token + barcode on equipment, warranty/AMC with daily
status cron, inspections updating condition/health, transfer/disposal workflow models with
OWL Operations screen, extended asset detail tabs, dashboard KPIs for expiring contracts and
pending workflows, maintenance request guard on disposed assets, PDF asset label report stub.

**Phase 5 (done, v18.0.4.0.0):** FMS depreciation schedules (`fms.asset.depreciation.schedule` /
`fms.asset.depreciation.line`) with straight-line and declining-balance generation, daily cron to
post due periods, computed book value on equipment, disposal default book value, dashboard finance
KPIs, OWL financial tab, per-company **Accounting Bridge** config (optional GL posting when
`account` is installed — still no hard dependency on Accounting).

**Phase 6 (done, v18.0.5.0.0):** OWL UI parity with Fire & Safety shell (top bar search, role chip,
avatar, configuration shortcut), reusable KPI / empty / alert components, polished dashboard with
quick actions and two-column analytics, register table enhancements (health, book value), detail
hero styling, global search routing to register.

**Phase 7 (done, v18.0.6.0.0):** release validator (`fms.asset.validation`), end-to-end integration
tests (registration → operations → maintenance → depreciation → disposal), cron smoke, expanded
RBAC/multi-company tests, `docs/VALIDATION.md` + `CHANGELOG.md`, install checks for crons and reports.

## Install path (repository layout)

The addon lives under `/Users/palakboricha/Desktop/asset_management/fms_asset_management`.
Add **`/Users/palakboricha/Desktop/asset_management`** to Odoo `--addons-path` (not `fmss`).

See the repo root `README.md` for install, update, test, and server commands.
