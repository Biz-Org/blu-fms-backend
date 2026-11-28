# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


# Default weights (must sum to 1.0)
WEIGHTS = {
    'quality': 0.25,
    'safety': 0.25,
    'sla': 0.20,
    'compliance': 0.15,
    'attendance': 0.15,
}


class VcEvaluation(models.Model):
    _name = 'vc.evaluation'
    _description = 'Vendor / Contractor Evaluation'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'vc.api.mixin']
    _order = 'evaluation_date desc, id desc'

    name = fields.Char(string='Evaluation Reference', copy=False, readonly=True, default='New')
    vendor_id = fields.Many2one('vc.vendor', ondelete='cascade', index=True)
    contractor_id = fields.Many2one('vc.contractor', ondelete='cascade', index=True)
    contract_id = fields.Many2one('vc.contract', ondelete='set null')
    site_id = fields.Many2one('vc.site')
    evaluation_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    evaluator_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    quality_score = fields.Float(default=0.0)
    safety_score = fields.Float(default=0.0)
    sla_score = fields.Float(default=0.0)
    compliance_score = fields.Float(default=0.0)
    attendance_score = fields.Float(default=0.0)
    overall_score = fields.Float(compute='_compute_overall', store=True)
    rating = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('average', 'Average'),
        ('poor', 'Poor'),
    ], compute='_compute_overall', store=True)
    comments = fields.Text()
    improvement_notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ], default='draft', tracking=True)

    @api.depends(
        'quality_score', 'safety_score', 'sla_score',
        'compliance_score', 'attendance_score',
    )
    def _compute_overall(self):
        for rec in self:
            score = (
                (rec.quality_score or 0.0) * WEIGHTS['quality']
                + (rec.safety_score or 0.0) * WEIGHTS['safety']
                + (rec.sla_score or 0.0) * WEIGHTS['sla']
                + (rec.compliance_score or 0.0) * WEIGHTS['compliance']
                + (rec.attendance_score or 0.0) * WEIGHTS['attendance']
            )
            rec.overall_score = round(score, 2)
            if score >= 85:
                rec.rating = 'excellent'
            elif score >= 70:
                rec.rating = 'good'
            elif score >= 50:
                rec.rating = 'average'
            else:
                rec.rating = 'poor'

    @api.constrains(
        'quality_score', 'safety_score', 'sla_score',
        'compliance_score', 'attendance_score',
    )
    def _check_scores(self):
        for rec in self:
            for field_name in (
                'quality_score', 'safety_score', 'sla_score',
                'compliance_score', 'attendance_score',
            ):
                val = rec[field_name]
                if val is not False and (val < 0 or val > 100):
                    raise ValidationError('Scores must be between 0 and 100.')

    @api.constrains('vendor_id', 'contractor_id')
    def _check_party(self):
        for rec in self:
            if not rec.vendor_id and not rec.contractor_id:
                raise ValidationError('Select a vendor or contractor for evaluation.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vc.evaluation') or 'EVAL-NEW'
        records = super().create(vals_list)
        for rec in records:
            self._vc_log('evaluation_created', rec, 'Evaluation created', new_state=rec.state)
        return records

    def action_submit(self):
        for rec in self:
            if rec.state == 'submitted':
                continue
            prev = rec.state
            rec.state = 'submitted'
            # Update vendor rating from latest evaluations
            if rec.vendor_id:
                evals = self.search([
                    ('vendor_id', '=', rec.vendor_id.id),
                    ('state', '=', 'submitted'),
                ])
                if evals:
                    avg = sum(evals.mapped('overall_score')) / len(evals)
                    rec.vendor_id.sudo().write({'rating': round(avg / 20.0, 2)})  # 0-5 scale
            self._vc_log('evaluation_submitted', rec, 'Evaluation submitted', prev, 'submitted')
        return True

    def to_api_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'code': self.name,
            'vendor_id': self.vendor_id.id or False,
            'vendor': self.vendor_id.name or '',
            'contractor_id': self.contractor_id.id or False,
            'contractor': self.contractor_id.name or '',
            'contract_id': self.contract_id.id or False,
            'site': self.site_id.name if self.site_id else '',
            'evaluation_date': self._vc_date(self.evaluation_date),
            'evaluator': self.evaluator_id.name,
            'quality_score': self.quality_score,
            'safety_score': self.safety_score,
            'sla_score': self.sla_score,
            'compliance_score': self.compliance_score,
            'attendance_score': self.attendance_score,
            'overall_score': self.overall_score,
            'rating': self.rating,
            'rating_label': self._vc_selection_label(self, 'rating'),
            'comments': self.comments or '',
            'improvement_notes': self.improvement_notes or '',
            'state': self.state,
        }
