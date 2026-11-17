# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

RATINGS = [
    ('1', '1 - Very Poor'),
    ('2', '2 - Poor'),
    ('3', '3 - Average'),
    ('4', '4 - Good'),
    ('5', '5 - Excellent'),
]


class FmsHelpdeskFeedback(models.Model):
    _name = 'fms.helpdesk.feedback'
    _description = 'Resident Feedback'
    _inherit = ['fms.helpdesk.access.mixin']
    _order = 'request_date desc, id desc'
    _rec_name = 'ticket_id'
    _check_company_auto = True

    ticket_id = fields.Many2one(
        'fms.helpdesk.ticket', string='Ticket', required=True, ondelete='cascade', index=True, check_company=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True, index=True)
    resident_id = fields.Many2one(related='ticket_id.resident_id', store=True, string='Resident')
    category_id = fields.Many2one(related='ticket_id.category_id', store=True, string='Category')
    team_id = fields.Many2one(related='ticket_id.team_id', store=True, string='Support Team')
    resolved_by_id = fields.Many2one(related='ticket_id.resolved_by_id', store=True, string='Resolved By')
    state = fields.Selection(
        [('pending', 'Pending'),
         ('submitted', 'Submitted'),
         ('reviewed', 'Reviewed')],
        default='pending', required=True, index=True)
    rating = fields.Selection(RATINGS)
    rating_value = fields.Integer(compute='_compute_rating', store=True, aggregator='avg')
    is_low_rating = fields.Boolean(compute='_compute_rating', store=True, index=True)
    comment = fields.Text()
    request_date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    submit_date = fields.Datetime(readonly=True)
    reviewed_by_id = fields.Many2one('res.users', readonly=True)
    review_date = fields.Datetime(readonly=True)
    review_note = fields.Text()

    @api.depends('rating')
    def _compute_rating(self):
        threshold = self.env['fms.helpdesk.ticket']._get_int_param('low_rating_threshold') or 2
        for feedback in self:
            feedback.rating_value = int(feedback.rating) if feedback.rating else 0
            feedback.is_low_rating = bool(feedback.rating) and feedback.rating_value <= threshold

    @api.constrains('state', 'rating')
    def _check_rating(self):
        for feedback in self:
            if feedback.state != 'pending' and not feedback.rating:
                raise ValidationError(_("Submitted feedback must have a rating."))

    def write(self, vals):
        if not self._fms_skip_privilege():
            submitting = vals.get('state') == 'submitted' or ('rating' in vals and vals.get('state') != 'reviewed')
            reviewing = vals.get('state') == 'reviewed'
            if reviewing and not self._fms_is_team_lead():
                self._fms_raise(_("review resident feedback"))
            if submitting and not reviewing:
                if self._fms_is_resident():
                    if any(not self._fms_owns_ticket(feedback.ticket_id) for feedback in self):
                        self._fms_raise(_("submit feedback on another resident's ticket"))
                elif not self._fms_is_team_lead():
                    self._fms_raise(_("submit resident feedback"))
        if vals.get('rating') and 'state' not in vals:
            vals = dict(vals, state='submitted')
        if vals.get('state') == 'submitted':
            vals.setdefault('submit_date', fields.Datetime.now())
        if vals.get('state') == 'reviewed':
            vals.setdefault('reviewed_by_id', self.env.uid)
            vals.setdefault('review_date', fields.Datetime.now())
        result = super().write(vals)
        if 'rating' in vals or 'state' in vals:
            labels = dict(self._fields['rating']._description_selection(self.env))
            for feedback in self:
                feedback.ticket_id._log_history(
                    'feedback', new_value=labels.get(feedback.rating, ''),
                    remarks=feedback.review_note if feedback.state == 'reviewed' else feedback.comment)
        return result
