# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FmsHelpdeskCategory(models.Model):
    _name = 'fms.helpdesk.category'
    _description = 'Complaint Category'
    _inherit = ['mail.thread', 'fms.helpdesk.config.mixin']
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True, tracking=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text(translate=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    default_team_id = fields.Many2one(
        'fms.helpdesk.team', string='Default Support Team', check_company=True, tracking=True)
    default_user_id = fields.Many2one(
        'res.users', string='Default Assignee', domain=[('share', '=', False)], tracking=True)
    default_priority_id = fields.Many2one('fms.helpdesk.priority', string='Default Priority')
    auto_routing = fields.Boolean(
        string='Apply Routing Rules', default=True,
        help="When disabled, tickets of this category go straight to the default team/assignee.")
    subcategory_ids = fields.One2many('fms.helpdesk.subcategory', 'category_id', string='Subcategories')
    routing_rule_ids = fields.One2many('fms.helpdesk.routing.rule', 'category_id', string='Routing Rules')
    subcategory_count = fields.Integer(compute='_compute_counts')
    routing_rule_count = fields.Integer(compute='_compute_counts')
    subcategory_summary = fields.Char(compute='_compute_counts')
    routing_rule_summary = fields.Char(compute='_compute_counts')

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'A category with this name already exists.'),
    ]

    @api.depends('subcategory_ids', 'routing_rule_ids')
    def _compute_counts(self):
        for category in self:
            sub_count = len(category.subcategory_ids)
            rule_count = len(category.routing_rule_ids)
            category.subcategory_count = sub_count
            category.routing_rule_count = rule_count
            category.subcategory_summary = _('%s subcat', sub_count)
            category.routing_rule_summary = _('%s rules', rule_count)

    @api.constrains('default_team_id', 'default_user_id')
    def _check_default_user_in_team(self):
        Team = self.env['fms.helpdesk.team']
        for category in self:
            if not Team._check_user_in_team(category.default_team_id, category.default_user_id):
                raise ValidationError(_(
                    "The default assignee of category '%(category)s' must be a member of team '%(team)s'.",
                    category=category.name, team=category.default_team_id.name))

    def action_open_routing_test(self):
        context = dict(self.env.context)
        if self:
            context['default_category_id'] = self[0].id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Test Routing'),
            'res_model': 'fms.helpdesk.routing.test',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    def action_open_routing_rules(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Routing Rules'),
            'res_model': 'fms.helpdesk.routing.rule',
            'view_mode': 'list,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id, 'default_team_id': self.default_team_id.id},
        }


class FmsHelpdeskSubcategory(models.Model):
    _name = 'fms.helpdesk.subcategory'
    _description = 'Complaint Subcategory'
    _inherit = ['fms.helpdesk.config.mixin']
    _order = 'category_id, sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    category_id = fields.Many2one(
        'fms.helpdesk.category', string='Category', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='category_id.company_id', store=True, index=True)
    default_priority_id = fields.Many2one('fms.helpdesk.priority', string='Default Priority')

    _sql_constraints = [
        ('name_category_uniq', 'unique(name, category_id)',
         'This subcategory already exists in the selected category.'),
    ]
