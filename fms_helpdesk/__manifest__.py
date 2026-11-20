# -*- coding: utf-8 -*-
{
    'name': 'FMS Helpdesk',
    'version': '18.0.1.15.1',
    'category': 'Services/Helpdesk',
    'summary': 'Complaint & Helpdesk Management for the Facility Management System',
    'description': """
FMS Complaint & Helpdesk Management
===================================
Resident complaint and service-request lifecycle: ticket registration,
category-based routing, assignment, priority and SLA timers, escalation,
resolution and verification, closure, reopening, resident feedback and a
protected audit trail.
    """,
    'author': 'Bizlem',
    'website': 'https://www.bizlem.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'resource'],
    'data': [
        'security/fms_helpdesk_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/fms_helpdesk_master_data.xml',
        'data/ir_config_parameter_data.xml',
        'data/ir_cron_data.xml',
        'views/fms_helpdesk_team_views.xml',
        'views/fms_helpdesk_category_views.xml',
        'views/fms_helpdesk_routing_views.xml',
        'views/fms_helpdesk_ticket_views.xml',
        'views/fms_helpdesk_app_views.xml',
        'views/fms_helpdesk_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'fms_helpdesk/static/src/scss/fms_helpdesk.scss',
            'fms_helpdesk/static/src/js/helpdesk_app.js',
            'fms_helpdesk/static/src/xml/helpdesk_app.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
