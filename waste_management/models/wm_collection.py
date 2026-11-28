# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmCollectionSchedule(models.Model):
    _name = 'wm.collection.schedule'
    _description = 'Waste Collection Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'pickup_date desc, id desc'

    name = fields.Char(string='Schedule Reference', copy=False, readonly=True, default='New')
    entry_id = fields.Many2one('wm.entry', ondelete='set null', tracking=True)
    entry_ids = fields.Many2many('wm.entry', string='Waste Entries')
    waste_category = fields.Selection(related='entry_id.waste_category', store=True)
    quantity = fields.Float(required=True, default=0.0)
    uom_id = fields.Many2one('uom.uom', default=lambda self: self.env.ref('uom.product_uom_kgm', raise_if_not_found=False))
    pickup_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    time_from = fields.Float(string='From (hours)', default=10.0)
    time_to = fields.Float(string='To (hours)', default=11.0)
    vendor_id = fields.Many2one('wm.vendor', tracking=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    driver_id = fields.Many2one('hr.employee', string='Driver')
    site = fields.Char(required=True, default='Main Facility')
    destination = fields.Char()
    location_id = fields.Many2one('stock.location', string='Pickup Location')
    dest_location_id = fields.Many2one('stock.location', string='Destination Location')
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], default='medium')
    notes = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('delayed', 'Delayed'),
        ('missed', 'Missed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)
    pickup_ids = fields.One2many('wm.pickup.tracking', 'schedule_id')

    @api.constrains('quantity', 'pickup_date', 'time_from', 'time_to')
    def _check_values(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError('Collection quantity must be greater than zero.')
            if rec.time_to and rec.time_from and rec.time_to < rec.time_from:
                raise ValidationError('End time must be after start time.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.collection.schedule') or 'WM-COL-NEW'
            if vals.get('entry_id') and not vals.get('quantity'):
                vals['quantity'] = self.env['wm.entry'].browse(vals['entry_id']).quantity
            if vals.get('entry_id') and not vals.get('site'):
                vals['site'] = self.env['wm.entry'].browse(vals['entry_id']).site
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('collection_created', rec, 'Collection schedule created', new_value=rec.state)
        return records

    def _fmt_window(self):
        self.ensure_one()

        def _h(val):
            hours = int(val or 0)
            minutes = int(round(((val or 0) - hours) * 60))
            return '%02d:%02d' % (hours, minutes)

        return '%s–%s' % (_h(self.time_from), _h(self.time_to))

    def action_schedule(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft',), 'schedule')
            if not rec.vendor_id:
                raise UserError('Assign a collection vendor before scheduling.')
            prev = rec.state
            rec.state = 'scheduled'
            # create pickup tracking shell
            if not rec.pickup_ids:
                self.env['wm.pickup.tracking'].create({
                    'schedule_id': rec.id,
                    'entry_id': rec.entry_id.id,
                    'vendor_id': rec.vendor_id.id,
                    'vehicle_id': rec.vehicle_id.id,
                    'driver_id': rec.driver_id.id,
                    'planned_date': rec.pickup_date,
                    'planned_qty': rec.quantity,
                    'site': rec.site,
                })
            self._wm_log('collection_scheduled', rec, 'Collection scheduled', prev, 'scheduled')
        return True

    def action_confirm(self):
        for rec in self:
            self._wm_assert_transition(rec, ('scheduled', 'draft'), 'confirm')
            prev = rec.state
            rec.state = 'confirmed'
            self._wm_log('collection_confirmed', rec, 'Collection confirmed', prev, 'confirmed')
        return True

    def action_start(self):
        for rec in self:
            self._wm_assert_transition(rec, ('scheduled', 'confirmed'), 'start')
            prev = rec.state
            rec.state = 'in_progress'
            for pickup in rec.pickup_ids.filtered(lambda p: p.state in ('pending', 'ready')):
                pickup.action_start()
            self._wm_log('collection_started', rec, 'Collection started', prev, 'in_progress')
        return True

    def action_complete(self):
        for rec in self:
            self._wm_assert_transition(rec, ('in_progress', 'confirmed', 'scheduled'), 'complete')
            prev = rec.state
            rec.state = 'completed'
            for pickup in rec.pickup_ids.filtered(lambda p: p.state != 'completed'):
                if pickup.state in ('pending', 'ready'):
                    pickup.action_start()
                if pickup.state != 'completed':
                    pickup.action_complete()
            self._wm_log('collection_completed', rec, 'Collection completed', prev, 'completed')
        return True

    def action_cancel(self):
        for rec in self:
            self._wm_assert_transition(rec, ('draft', 'scheduled', 'confirmed'), 'cancel')
            prev = rec.state
            rec.state = 'cancelled'
            self._wm_log('collection_cancelled', rec, 'Collection cancelled', prev, 'cancelled')
        return True

    @api.model
    def cron_mark_overdue(self):
        today = fields.Date.context_today(self)
        overdue = self.search([
            ('pickup_date', '<', today),
            ('state', 'in', ('scheduled', 'confirmed', 'draft')),
        ])
        for rec in overdue:
            prev = rec.state
            rec.state = 'delayed'
            self._wm_log('collection_overdue', rec, 'Collection marked overdue', prev, 'delayed')
            for pickup in rec.pickup_ids.filtered(lambda p: p.state in ('pending', 'ready', 'en_route')):
                pickup.action_delay()
        return True

    def to_api_dict(self):
        self.ensure_one()
        prio_map = {'high': 'bad', 'medium': 'warn', 'low': 'info'}
        status_map = {
            'draft': ('Draft', 'info'),
            'scheduled': ('Scheduled', 'info'),
            'confirmed': ('Confirmed', 'info'),
            'in_progress': ('In Progress', 'warn'),
            'completed': ('Completed', 'ok'),
            'delayed': ('Overdue', 'bad'),
            'missed': ('Missed', 'bad'),
            'cancelled': ('Cancelled', 'bad'),
        }
        status, status_key = status_map.get(self.state, (self.state, 'info'))
        return {
            'id': self.id,
            'priority': dict(self._fields['priority'].selection).get(self.priority, ''),
            'priorityKey': prio_map.get(self.priority, 'warn'),
            'code': self.name,
            'entry': self.entry_id.code if self.entry_id else '',
            'entry_id': self.entry_id.id or False,
            'datetime': '%s, %s' % (self._wm_date(self.pickup_date), self._fmt_window()),
            'site': self.site or '',
            'type': self.entry_id.waste_type if self.entry_id else (self.waste_category or ''),
            'qty': '%s %s' % (self.quantity, self.uom_id.name or 'kg'),
            'vendor': self.vendor_id.name if self.vendor_id else '',
            'status': status,
            'statusKey': status_key,
            'state': self.state,
        }


class WmPickupTracking(models.Model):
    _name = 'wm.pickup.tracking'
    _description = 'Waste Pickup Tracking'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'wm.api.mixin']
    _order = 'planned_date desc, id desc'

    name = fields.Char(string='Tracking Reference', copy=False, readonly=True, default='New')
    schedule_id = fields.Many2one('wm.collection.schedule', required=True, ondelete='cascade')
    entry_id = fields.Many2one('wm.entry', ondelete='set null')
    vendor_id = fields.Many2one('wm.vendor')
    vehicle_id = fields.Many2one('fleet.vehicle')
    driver_id = fields.Many2one('hr.employee')
    planned_date = fields.Date()
    actual_date = fields.Datetime()
    planned_qty = fields.Float()
    collected_qty = fields.Float()
    site = fields.Char()
    destination = fields.Char()
    eta = fields.Char()
    attachment_ids = fields.Many2many('ir.attachment', string='Proof')
    remarks = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('en_route', 'En Route'),
        ('arrived', 'Arrived'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('delayed', 'Delayed'),
        ('exception', 'Exception'),
        ('cancelled', 'Cancelled'),
    ], default='pending', tracking=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('wm.pickup.tracking') or 'WM-PICK-NEW'
        records = super().create(vals_list)
        for rec in records:
            self._wm_log('pickup_created', rec, 'Pickup tracking created', new_value=rec.state)
        return records

    def action_start(self):
        for rec in self:
            self._wm_assert_transition(rec, ('pending', 'ready'), 'start')
            prev = rec.state
            rec.state = 'en_route'
            self._wm_log('pickup_started', rec, 'Pickup en route', prev, 'en_route')
        return True

    def action_arrive(self):
        for rec in self:
            self._wm_assert_transition(rec, ('en_route', 'ready'), 'arrive')
            prev = rec.state
            rec.state = 'arrived'
            self._wm_log('pickup_arrived', rec, 'Pickup arrived', prev, 'arrived')
        return True

    def action_collect(self, quantity=None):
        for rec in self:
            self._wm_assert_transition(rec, ('arrived', 'en_route', 'picked_up'), 'collect')
            vals = {'state': 'picked_up', 'actual_date': fields.Datetime.now()}
            if quantity is not None:
                vals['collected_qty'] = quantity
            prev = rec.state
            rec.write(vals)
            self._wm_log('pickup_collected', rec, 'Waste picked up', prev, 'picked_up')
        return True

    def action_complete(self):
        for rec in self:
            self._wm_assert_transition(
                rec, ('picked_up', 'in_transit', 'delivered', 'arrived', 'en_route'), 'complete'
            )
            if not rec.collected_qty:
                rec.collected_qty = rec.planned_qty
            prev = rec.state
            rec.write({'state': 'completed', 'actual_date': rec.actual_date or fields.Datetime.now()})
            if rec.schedule_id.state != 'completed':
                rec.schedule_id.state = 'completed'
            self._wm_log('pickup_completed', rec, 'Pickup completed', prev, 'completed')
        return True

    def action_delay(self):
        for rec in self:
            prev = rec.state
            rec.state = 'delayed'
            if rec.schedule_id:
                rec.schedule_id.state = 'delayed'
            self._wm_log('pickup_delayed', rec, 'Pickup delayed', prev, 'delayed')
        return True

    def to_api_dict(self):
        self.ensure_one()
        status_map = {
            'pending': ('Pending', 'warn'),
            'ready': ('Ready', 'info'),
            'en_route': ('En Route', 'info'),
            'arrived': ('Arrived', 'warn'),
            'picked_up': ('Collected', 'ok'),
            'in_transit': ('In Transit', 'info'),
            'delivered': ('Delivered', 'ok'),
            'completed': ('Completed', 'ok'),
            'delayed': ('Delayed', 'bad'),
            'exception': ('Exception', 'bad'),
            'cancelled': ('Cancelled', 'bad'),
        }
        status, status_key = status_map.get(self.state, (self.state, 'info'))
        return {
            'id': self.id,
            'code': self.name,
            'collection': self.schedule_id.name if self.schedule_id else '',
            'schedule_id': self.schedule_id.id,
            'vendor': self.vendor_id.name if self.vendor_id else '',
            'driver': self.driver_id.name if self.driver_id else '',
            'site': self.site or '',
            'expected': '%s kg' % (self.planned_qty or 0),
            'actual': ('%s kg' % self.collected_qty) if self.collected_qty else '—',
            'status': status,
            'statusKey': status_key,
            'eta': self.eta or '—',
            'state': self.state,
        }
