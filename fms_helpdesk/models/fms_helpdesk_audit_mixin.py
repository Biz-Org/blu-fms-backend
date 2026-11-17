# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class FmsHelpdeskAuditMixin(models.AbstractModel):
    """Append-only records: they can be created (by the system) but never edited or deleted."""

    _name = 'fms.helpdesk.audit.mixin'
    _description = 'Helpdesk Append-only Audit Record'

    def write(self, vals):
        raise UserError(_("%s is an audit trail and cannot be modified.", self._description))

    def unlink(self):
        # Parent ticket/admin delete uses this flag so cascade cleanup can succeed.
        if self.env.context.get('fms_allow_audit_unlink'):
            return super().unlink()
        raise UserError(_("%s is an audit trail and cannot be deleted.", self._description))
