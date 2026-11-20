# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext


class FmsHelpdeskResolution(models.Model):
    _name = 'fms.helpdesk.resolution'
    _description = 'Ticket Resolution'
    _inherit = ['fms.helpdesk.access.mixin']
    _order = 'resolved_date desc, id desc'
    _rec_name = 'ticket_id'
    _check_company_auto = True

    ticket_id = fields.Many2one(
        'fms.helpdesk.ticket', string='Ticket', required=True, ondelete='cascade', index=True, check_company=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True, index=True)
    description = fields.Html(string='Resolution', required=True)
    work_performed = fields.Text()
    resolved_by_id = fields.Many2one(
        'res.users', string='Resolved By', required=True, default=lambda self: self.env.user)
    resolved_date = fields.Datetime(string='Resolved On', required=True, default=fields.Datetime.now)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'fms_helpdesk_resolution_attachment_rel', 'resolution_id', 'attachment_id',
        string='Resolution Evidence')
    state = fields.Selection(
        [('submitted', 'Submitted'),
         ('verified', 'Verified'),
         ('rejected', 'Rejected')],
        default='submitted', required=True, readonly=True, index=True)
    verified_by_id = fields.Many2one('res.users', string='Verified By', readonly=True)
    verified_date = fields.Datetime(readonly=True)
    verification_remarks = fields.Text(readonly=True)

    @api.constrains('attachment_ids')
    def _check_attachments(self):
        Ticket = self.env['fms.helpdesk.ticket']
        for resolution in self:
            Ticket._check_attachment_policy(resolution.attachment_ids)

    def _fms_can_verify(self, ticket):
        if self._fms_is_team_lead():
            return True
        return self._fms_is_resident() and self._fms_owns_ticket(ticket)

    @api.model_create_multi
    def create(self, vals_list):
        if not self._fms_skip_privilege() and not self._fms_is_agent():
            self._fms_raise(_("record a resolution"))
        resolutions = super().create(vals_list)
        require_verification = self.env['fms.helpdesk.ticket']._get_bool_param('require_verification')
        for resolution in resolutions:
            ticket = resolution.ticket_id
            if ticket.state in ('draft', 'closed'):
                raise ValidationError(_("A resolution cannot be added to a draft or closed ticket."))
            resolution.attachment_ids.sudo().filtered(lambda a: not a.res_id).write(
                {'res_model': self._name, 'res_id': resolution.id})
            ticket._log_history(
                'resolution', new_value=html2plaintext(resolution.description or '').strip()[:2000],
                remarks=resolution.work_performed)
            target = 'awaiting_verification' if require_verification else 'resolved'
            if ticket.state != target:
                ticket.write({'state': target})
        return resolutions

    def write(self, vals):
        if not self._fms_skip_privilege() and self._fms_is_resident() and not self._fms_is_team_lead():
            allowed = {'state', 'verified_by_id', 'verified_date', 'verification_remarks'}
            if set(vals) - allowed:
                self._fms_raise(_("edit a resolution"))
        return super().write(vals)

    def action_verify(self, remarks=False):
        self._set_verification('verified', remarks)

    def action_reject(self, remarks=False):
        if not (remarks or '').strip():
            raise UserError(_("Please explain why the resolution is rejected."))
        self._set_verification('rejected', remarks)
        for ticket in self.ticket_id:
            ticket.with_context(fms_history_remarks=remarks, fms_from_verification=True).write({'state': 'in_progress'})

    def _set_verification(self, result, remarks):
        for resolution in self:
            if not self._fms_can_verify(resolution.ticket_id):
                self._fms_raise(_("verify or reject a resolution"))
            if resolution.state != 'submitted':
                raise UserError(_("Only submitted resolutions can be verified or rejected."))
        self.write({
            'state': result,
            'verified_by_id': self.env.uid,
            'verified_date': fields.Datetime.now(),
            'verification_remarks': remarks or False,
        })
        label = dict(self._fields['state']._description_selection(self.env))[result]
        for resolution in self:
            resolution.ticket_id._log_history('verification', new_value=label, remarks=remarks)
