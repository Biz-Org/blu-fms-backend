# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            equipment_id = vals.get("equipment_id")
            if equipment_id:
                equipment = self.env["maintenance.equipment"].browse(equipment_id)
                if equipment.fms_operations_locked:
                    raise ValidationError(
                        _("Cannot create maintenance requests for disposed asset %s.", equipment.display_name)
                    )
        return super().create(vals_list)