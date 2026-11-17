# FMS Asset Management (Odoo 18)

Addon path: `fms_asset_management/` in this directory. Current release: **18.0.6.0.0** (Phase 7 — integration validation, release hardening).

See `fms_asset_management/docs/VALIDATION.md` for the release checklist and `fms_asset_management/CHANGELOG.md` for version history.

## Environment

```bash
export ODOO=/Users/palakboricha/Documents/odoo
export ASSET_ADDONS=/Users/palakboricha/Desktop/asset_management
export FMSS=/Users/palakboricha/fmss
export ADDONS="$ODOO/odoo/addons,$ODOO/addons,$ASSET_ADDONS,$FMSS"
export DB=fms_dev
export DATA_DIR="$FMSS/.odoo-data-18"
```

Include `$FMSS` only if you need other FMS modules (Fire & Safety, Compliance, etc.) from that tree.

On macOS, if `libpq` errors appear:

```bash
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/opt/libpq/lib:/opt/homebrew/opt/openssl@3/lib"
```

## First install

```bash
cd "$ODOO"

.venv/bin/python odoo-bin \
  --addons-path="$ADDONS" \
  -d "$DB" \
  -i fms_asset_management \
  --stop-after-init \
  --db_host=127.0.0.1 \
  --db_port=5432 \
  --data-dir="$DATA_DIR"
```

## Update after code changes

```bash
cd "$ODOO"

.venv/bin/python odoo-bin \
  --addons-path="$ADDONS" \
  -d "$DB" \
  -u fms_asset_management \
  --stop-after-init \
  --db_host=127.0.0.1 \
  --db_port=5432 \
  --data-dir="$DATA_DIR"
```

## Run tests

```bash
cd "$ODOO"

.venv/bin/python odoo-bin \
  --addons-path="$ADDONS" \
  -d "$DB" \
  -u fms_asset_management \
  --stop-after-init \
  --db_host=127.0.0.1 \
  --db_port=5432 \
  --data-dir="$DATA_DIR" \
  --test-enable \
  --test-tags /fms_asset_management
```

## Start dev server

```bash
cd "$ODOO"

.venv/bin/python odoo-bin \
  --addons-path="$ADDONS" \
  -d "$DB" \
  --http-port=8072 \
  --http-interface=127.0.0.1 \
  --db_host=127.0.0.1 \
  --db_port=5432 \
  --data-dir="$DATA_DIR" \
  --dev=xml,assets
```

Open http://127.0.0.1:8072
