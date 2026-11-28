{
    'name': 'Housekeeping Management',
    'version': '18.0.2.1',
    'category': 'Operations/Housekeeping',
    'summary': 'CleanSync Pro housekeeping operations backend and UI',
    'description': """
Housekeeping Management
=======================
Full backend for CleanSync Pro: staff, roster, zones, schedules, tasks,
checklists, verification, consumables and performance.
    """,
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/housekeeping_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/sample_data.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'housekeeping_management/static/src/dashboard/dashboard.scss',
            'housekeeping_management/static/src/dashboard/responsive.scss',
            'housekeeping_management/static/src/dashboard/dashboard.xml',
            'housekeeping_management/static/src/dashboard/dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
