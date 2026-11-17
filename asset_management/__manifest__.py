# -*- coding: utf-8 -*-
{
    "name": "Asset Management",
    "version": "18.0.6.0.0",
    "category": "Services/Asset Management",
    "summary": "FMS asset lifecycle, classification, and facility location management",
    "description": """
Asset Management for facility management (FMS module #13).

Extends Odoo Maintenance equipment as the canonical operational asset record
and provides FMS-owned classification, facility locations, lifecycle fields,
and OWL UI aligned with other FMS modules.
    """,
    "author": "FMS",
    "license": "LGPL-3",
    "application": True,
    "installable": True,
    "depends": [
        "maintenance",
        "mail",
    ],
    "data": [
        "security/asset_groups.xml",
        "security/ir.model.access.csv",
        "security/asset_rules.xml",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "report/asset_label_report.xml",
        "views/maintenance_equipment_views.xml",
        "views/depreciation_views.xml",
        "views/operations_views.xml",
        "views/classification_views.xml",
        "views/location_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "fms_asset_management/static/src/scss/_tokens.scss",
            "fms_asset_management/static/src/scss/fms_asset_management.scss",
            "fms_asset_management/static/src/owl/ui/**/*",
            "fms_asset_management/static/src/owl/screens/**/*",
        ],
    },
}
