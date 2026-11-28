# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class VcCron(models.TransientModel):
    _name = 'vc.cron'
    _description = 'Vendor Contractor Scheduled Jobs'

    @api.model
    def run_all_maintenance(self):
        """Idempotent batch: expiry scans + compliance refresh notifications."""
        try:
            self.env['vc.document'].cron_scan_expiry()
        except Exception:
            _logger.exception('VC document expiry scan failed')
        try:
            self.env['vc.contract'].cron_scan_expiry()
        except Exception:
            _logger.exception('VC contract expiry scan failed')
        try:
            self.env['vc.daily.pass'].cron_scan_expiry()
        except Exception:
            _logger.exception('VC daily pass expiry scan failed')
        try:
            self.env['vc.ptw'].cron_scan_expiry()
        except Exception:
            _logger.exception('VC PTW expiry scan failed')
        try:
            self._notify_pending_verifications()
        except Exception:
            _logger.exception('VC pending verification notify failed')
        return True

    @api.model
    def _notify_pending_verifications(self):
        mixin = self.env['vc.api.mixin']
        for vendor in self.env['vc.vendor'].search([
            ('state', 'in', ('submitted', 'under_verification', 'pending_verification', 'pending_approval')),
        ], limit=50):
            mixin._vc_notify(
                'Vendor pending verification',
                '%s awaits verification' % vendor.name,
                'vendor', vendor._name, vendor.id, 'info',
            )
        for contractor in self.env['vc.contractor'].search([
            ('state', 'in', ('submitted', 'pending', 'under_verification')),
        ], limit=50):
            mixin._vc_notify(
                'Contractor pending verification',
                '%s awaits verification' % contractor.name,
                'contractor', contractor._name, contractor.id, 'info',
            )
        # Compliance failures
        for vendor in self.env['vc.vendor'].search([
            ('compliance_state', '=', 'non_compliant'),
            ('state', 'in', ('active', 'approved')),
        ], limit=30):
            mixin._vc_notify(
                'Compliance failure',
                '%s is non-compliant' % vendor.name,
                'compliance', vendor._name, vendor.id, 'critical',
            )
        return True
