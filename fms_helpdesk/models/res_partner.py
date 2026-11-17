# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fms_is_resident = fields.Boolean(string='Is Resident')
    fms_property_name = fields.Char(string='Property')
    fms_building_name = fields.Char(string='Building / Tower')
    fms_floor_name = fields.Char(string='Floor')
    fms_unit_name = fields.Char(string='Apartment / Unit')
    fms_ticket_ids = fields.One2many('fms.helpdesk.ticket', 'resident_id', string='Helpdesk Tickets')
    fms_ticket_count = fields.Integer(compute='_compute_fms_ticket_count')

    def _compute_fms_ticket_count(self):
        counts = dict(self.env['fms.helpdesk.ticket']._read_group(
            [('resident_id', 'in', self.ids)], ['resident_id'], ['__count']))
        for partner in self:
            partner.fms_ticket_count = counts.get(partner, 0)
