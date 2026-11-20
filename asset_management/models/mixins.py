# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class FmsAssetWorkflowMixin(models.AbstractModel):
    _name = "fms.asset.workflow.mixin"
    _description = "Controlled FMS Asset workflow transitions"

    _fms_workflow_transitions = {}

    def write(self, vals):
        if "state" in vals and not self.env.context.get("fms_allow_state_write") and not self.env.su:
            changing = self.filtered(lambda rec: rec.state != vals["state"])
            if changing:
                raise UserError(_("Use the workflow actions to change record state."))
        return super().write(vals)

    def _fms_set_state(self, new_state):
        transitions = self._fms_workflow_transitions
        for record in self:
            if new_state == record.state:
                continue
            allowed = transitions.get(record.state, set())
            if new_state not in allowed:
                raise UserError(
                    _("Cannot change %(name)s from %(current)s to %(target)s.")
                    % {
                        "name": record.display_name,
                        "current": record.state,
                        "target": new_state,
                    }
                )
        self.with_context(fms_allow_state_write=True).write({"state": new_state})
        return True