# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class FmsHelpdeskRoutingTest(models.TransientModel):
    _name = 'fms.helpdesk.routing.test'
    _description = 'Test Ticket Routing'

    category_id = fields.Many2one('fms.helpdesk.category', string='Category', required=True)
    subcategory_id = fields.Many2one(
        'fms.helpdesk.subcategory', string='Subcategory',
        domain="[('category_id', '=', category_id)]")
    priority_id = fields.Many2one('fms.helpdesk.priority', string='Priority')
    rule_id = fields.Many2one('fms.helpdesk.routing.rule', string='Matched Rule', readonly=True)
    team_id = fields.Many2one('fms.helpdesk.team', string='Support Team', readonly=True)
    user_id = fields.Many2one('res.users', string='Assignee', readonly=True)
    sla_policy_id = fields.Many2one('fms.helpdesk.sla.policy', string='SLA Policy', readonly=True)
    result_summary = fields.Text(string='Result', readonly=True)

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.subcategory_id and self.subcategory_id.category_id != self.category_id:
            self.subcategory_id = False

    def action_test(self):
        self.ensure_one()
        rule = self.env['fms.helpdesk.routing.rule']._find_rule(
            self.category_id, self.subcategory_id, self.priority_id, self.env.company)
        team = rule.team_id or self.category_id.default_team_id
        user = rule.user_id or self.category_id.default_user_id
        if team and not user:
            user = team._get_next_assignee()
        policy = rule.sla_policy_id or self.env['fms.helpdesk.sla.policy']._find_policy(
            self.priority_id, self.category_id, self.env.company)
        if rule:
            summary = _('Matched rule "%(rule)s" → %(team)s → %(user)s → %(sla)s',
                        rule=rule.name,
                        team=team.display_name or _('No team'),
                        user=user.display_name or _('No assignee'),
                        sla=policy.display_name or _('No SLA policy'))
        else:
            summary = _('No routing rule matched. Fallback: %(team)s → %(user)s → %(sla)s',
                        team=team.display_name or _('No team'),
                        user=user.display_name or _('No assignee'),
                        sla=policy.display_name or _('No SLA policy'))
        self.write({
            'rule_id': rule.id,
            'team_id': team.id,
            'user_id': user.id,
            'sla_policy_id': policy.id,
            'result_summary': summary,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Test Routing'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
