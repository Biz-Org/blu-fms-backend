{
    'name': 'Waste Management',
    'version': '18.0.2.0',
    'category': 'Operations/Waste Management',
    'summary': 'FMS Waste Management — entries, segregation, collection, recycling, disposal and compliance',
    'description': """
Waste Management
================
End-to-end waste lifecycle for FMS: dashboard, waste entries, segregation,
collection schedule, pickup tracking, vendors, recycling, disposal, compliance,
analytics, settings and audit — backed by Odoo ORM and integrated with
contacts, products, inventory, fleet, HR and mail.
    """,
    'depends': [
        'base',
        'web',
        'mail',
        'product',
        'stock',
        'contacts',
        'fleet',
        'hr',
    ],
    'data': [
        'security/waste_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'waste_management/static/src/app/app.scss',
            'waste_management/static/src/app/responsive.scss',
            'waste_management/static/src/app/app.xml',
            'waste_management/static/src/app/demo_data.js',
            'waste_management/static/src/app/app.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
