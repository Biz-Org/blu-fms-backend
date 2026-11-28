{
    'name': 'Vendor & Contractor Management',
    'version': '18.0.2.1',
    'category': 'Operations/Vendor Contractor',
    'summary': 'External-party lifecycle: vendors, contractors, contracts, PTW and compliance',
    'description': """
Vendor & Contractor Management
==============================
Registration, onboarding, documents/compliance, contracts & AMC, workforce,
attendance & access, daily pass, Permit to Work, performance, reports and audit.
    """,
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/vendor_contractor_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/sample_data.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vendor_and_contractor_management/static/src/app/app.scss',
            'vendor_and_contractor_management/static/src/app/responsive.scss',
            'vendor_and_contractor_management/static/src/app/app.xml',
            'vendor_and_contractor_management/static/src/app/demo_data.js',
            'vendor_and_contractor_management/static/src/app/app.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
