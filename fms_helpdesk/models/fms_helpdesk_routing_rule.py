# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FmsHelpdeskRoutingRule(models.Model):
    _name = 'fms.helpdesk.routing.rule'
    _description = 'Helpdesk Routing Rule'
    _inherit = ['mail.thread', 'fms.helpdesk.config.mixin']
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(
        string='Rule Order', default=10, tracking=True,
        help="Rules are evaluated in ascending order; the first matching rule wins.")
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    category_id = fields.Many2one(
        'fms.helpdesk.category', string='Category', check_company=True, ondelete='cascade', tracking=True)
    subcategory_id = fields.Many2one(
        'fms.helpdesk.subcategory', string='Subcategory', ondelete='cascade', tracking=True,
        domain="[('category_id', '=', category_id)]")
    priority_id = fields.Many2one(
        'fms.helpdesk.priority', string='Priority', ondelete='restrict', tracking=True)

    team_id = fields.Many2one(
        'fms.helpdesk.team', string='Support Team', required=True, check_company=True,
        ondelete='restrict', tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Assignee', domain=[('share', '=', False)], tracking=True,
        help="Leave empty to let the team assignment method pick a member.")
    sla_policy_id = fields.Many2one(
        'fms.helpdesk.sla.policy', string='SLA Policy', check_company=True, ondelete='set null', tracking=True)

    @api.constrains('category_id', 'subcategory_id', 'priority_id')
    def _check_conditions(self):
        for rule in self:
            if not (rule.category_id or rule.subcategory_id or rule.priority_id):
                raise ValidationError(_("Routing rule '%s' needs at least one condition.", rule.name))
            if rule.subcategory_id and rule.subcategory_id.category_id != rule.category_id:
                raise ValidationError(_(
                    "Routing rule '%s': the subcategory does not belong to the selected category.", rule.name))

    @api.constrains('team_id', 'user_id')
    def _check_user_in_team(self):
        Team = self.env['fms.helpdesk.team']
        for rule in self:
            if not Team._check_user_in_team(rule.team_id, rule.user_id):
                raise ValidationError(_(
                    "Routing rule '%(rule)s': the assignee must be a member of team '%(team)s'.",
                    rule=rule.name, team=rule.team_id.name))

    @api.constrains('priority_id', 'sla_policy_id')
    def _check_sla_priority(self):
        for rule in self:
            if rule.priority_id and rule.sla_policy_id and rule.sla_policy_id.priority_id != rule.priority_id:
                raise ValidationError(_(
                    "Routing rule '%s': the SLA policy must be for the same priority as the rule.", rule.name))

    def _matches(self, category, subcategory, priority):
        self.ensure_one()
        return all((
            not self.category_id or self.category_id == category,
            not self.subcategory_id or self.subcategory_id == subcategory,
            not self.priority_id or self.priority_id == priority,
        ))

    @api.model
    def _find_rule(self, category, subcategory, priority, company=None):
        company = company or self.env.company
        rules = self.search([('company_id', 'in', [company.id, False])])
        return next((rule for rule in rules if rule._matches(category, subcategory, priority)), self.browse())
