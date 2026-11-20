# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import AccessError

GROUP_RESIDENT = 'fms_helpdesk.group_fms_helpdesk_resident'
GROUP_AGENT = 'fms_helpdesk.group_fms_helpdesk_agent'
GROUP_TEAM_LEAD = 'fms_helpdesk.group_fms_helpdesk_team_lead'
GROUP_MANAGER = 'fms_helpdesk.group_fms_helpdesk_manager'
GROUP_ADMIN = 'fms_helpdesk.group_fms_helpdesk_admin'


class FmsHelpdeskAccessMixin(models.AbstractModel):
    """Privilege helpers for Helpdesk roles. ACLs cover CRUD; these cover actions."""

    _name = 'fms.helpdesk.access.mixin'
    _description = 'Helpdesk Access Helpers'

    def _fms_is_admin(self):
        return self.env.su or self.env.user.has_group(GROUP_ADMIN)

    def _fms_is_manager(self):
        return self.env.su or self.env.user.has_group(GROUP_MANAGER)

    def _fms_is_team_lead(self):
        return self.env.su or self.env.user.has_group(GROUP_TEAM_LEAD)

    def _fms_is_agent(self):
        return self.env.su or self.env.user.has_group(GROUP_AGENT)

    def _fms_is_resident(self):
        user = self.env.user
        return bool(user.share) and user.has_group(GROUP_RESIDENT)

    def _fms_skip_privilege(self):
        return (
            self.env.su
            or self.env.context.get('fms_internal_write')
            or self.env.context.get('fms_assignment_type') == 'auto'
        )

    def _fms_raise(self, operation):
        raise AccessError(_("You are not allowed to %s.", operation))

    def _fms_owns_ticket(self, ticket):
        return bool(ticket.resident_id) and ticket.resident_id == self.env.user.partner_id


class FmsHelpdeskConfigMixin(models.AbstractModel):
    """Configuration records can only be created, changed or deleted by a Helpdesk Administrator."""

    _name = 'fms.helpdesk.config.mixin'
    _description = 'Helpdesk Configuration Access'
    _inherit = ['fms.helpdesk.access.mixin']

    def _fms_check_configure(self):
        if not self._fms_is_admin():
            self._fms_raise(_("change Helpdesk configuration"))

    @api.model_create_multi
    def create(self, vals_list):
        self._fms_check_configure()
        return super().create(vals_list)

    def write(self, vals):
        self._fms_check_configure()
        return super().write(vals)

    def unlink(self):
        self._fms_check_configure()
        return super().unlink()
