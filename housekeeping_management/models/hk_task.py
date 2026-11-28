from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HkTask(models.Model):
    _name = 'hk.task'
    _description = 'Cleaning Task'
    _order = 'date desc, time_start, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Cleaning Task', required=True, tracking=True)
    code = fields.Char(string='Task ID', copy=False, tracking=True)
    description = fields.Text()
    activity_id = fields.Many2one('hk.activity', string='Cleaning Activity')
    zone_id = fields.Many2one('hk.zone', required=True, ondelete='restrict', tracking=True)
    building = fields.Char(related='zone_id.building', store=True)
    floor = fields.Char(related='zone_id.floor', store=True)
    staff_id = fields.Many2one('hk.staff', string='Assigned Staff', ondelete='set null', tracking=True)
    shift_id = fields.Many2one('hk.shift', ondelete='set null')
    schedule_id = fields.Many2one('hk.schedule', ondelete='set null')
    date = fields.Date(required=True, index=True, default=fields.Date.context_today, tracking=True)
    time_start = fields.Float(string='Scheduled Start')
    time_end = fields.Float(string='Scheduled End')
    actual_start = fields.Datetime()
    actual_end = fields.Datetime()
    priority = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        default='medium',
        tracking=True,
    )
    source = fields.Selection(
        [('manual', 'Manual Task'), ('schedule', 'Schedule Generated')],
        default='manual',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('not_started', 'Not Started'),
            ('assigned', 'Assigned'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('verification_pending', 'Verification Pending'),
            ('verified', 'Verified'),
            ('rejected', 'Rejected'),
            ('rework', 'Rework'),
            ('cancelled', 'Cancelled'),
        ],
        default='not_started',
        required=True,
        tracking=True,
    )
    overdue = fields.Boolean(compute='_compute_overdue', store=True)
    highlight = fields.Boolean(string='Show On Dashboard')
    progress = fields.Float(string='Progress %', compute='_compute_progress', store=True)
    checklist_line_ids = fields.One2many('hk.task.checklist.line', 'task_id')
    checklist_template_id = fields.Many2one('hk.checklist.template')
    staff_remarks = fields.Text()
    issues = fields.Text()
    supervisor_comment = fields.Text()
    reject_reason = fields.Selection(
        [
            ('inadequate', 'Inadequate Cleaning'),
            ('incomplete', 'Incomplete Checklist'),
            ('missed', 'Missed Item'),
            ('evidence', 'Insufficient Evidence'),
            ('other', 'Other'),
        ],
    )
    verified_by = fields.Many2one('res.users')
    verified_date = fields.Datetime()
    consumable_usage_ids = fields.One2many('hk.consumable.usage', 'task_id')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Task ID must be unique.'),
    ]

    @api.depends('date', 'time_end', 'state')
    def _compute_overdue(self):
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        done = {'completed', 'verification_pending', 'verified', 'cancelled'}
        for task in self:
            if task.state in done:
                task.overdue = False
                continue
            if task.date and task.date < today:
                task.overdue = True
            elif task.date == today and task.time_end:
                hours = now.hour + now.minute / 60.0
                task.overdue = hours > task.time_end
            else:
                task.overdue = False

    @api.depends('checklist_line_ids.is_done', 'checklist_line_ids.is_mandatory')
    def _compute_progress(self):
        for task in self:
            lines = task.checklist_line_ids
            if not lines:
                task.progress = 100.0 if task.state in ('completed', 'verification_pending', 'verified') else 0.0
            else:
                task.progress = round(100.0 * len(lines.filtered('is_done')) / len(lines), 2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('hk.task') or '/'
            if vals.get('staff_id') and vals.get('state') in (False, 'not_started', 'draft'):
                if vals.get('state') != 'draft':
                    vals['state'] = 'assigned'
        tasks = super().create(vals_list)
        for task in tasks:
            if task.checklist_template_id and not task.checklist_line_ids:
                task._generate_checklist_lines()
            if task.staff_id and task.state == 'assigned':
                task.message_post(body='Task assigned to %s' % task.staff_id.name)
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if 'checklist_template_id' in vals:
            for task in self:
                if task.checklist_template_id and not task.checklist_line_ids:
                    task._generate_checklist_lines()
        return res

    def _generate_checklist_lines(self):
        self.ensure_one()
        template = self.checklist_template_id
        if not template:
            return
        self.checklist_line_ids.unlink()
        lines = []
        for item in template.item_ids:
            lines.append({
                'task_id': self.id,
                'name': item.name,
                'section': item.section,
                'sequence': item.sequence,
                'is_mandatory': item.is_mandatory,
                'instructions': item.instructions,
            })
        self.env['hk.task.checklist.line'].create(lines)

    def action_start(self):
        for task in self:
            if task.state not in ('assigned', 'not_started', 'rework'):
                raise UserError('Only assigned or rework tasks can be started.')
            task.write({'state': 'in_progress', 'actual_start': fields.Datetime.now()})
            if task.zone_id:
                task.zone_id.status = 'in_progress'
        return True

    def action_complete(self):
        for task in self:
            if task.state != 'in_progress':
                raise UserError('Only in-progress tasks can be completed.')
            task.write({'state': 'completed', 'actual_end': fields.Datetime.now(), 'progress': task.progress or 100.0})
        return True

    def action_submit_verification(self):
        for task in self:
            missing = task.checklist_line_ids.filtered(lambda l: l.is_mandatory and not l.is_done and not l.is_na)
            if missing:
                raise ValidationError('Complete all mandatory checklist items before submit:\n- %s' % '\n- '.join(missing.mapped('name')))
            task.write({'state': 'verification_pending', 'actual_end': task.actual_end or fields.Datetime.now()})
            if task.zone_id:
                task.zone_id.status = 'inspection'
            task.message_post(body='Checklist submitted for verification.')
            supervisors = self.env.ref('housekeeping_management.group_hk_supervisor').users
            for user in supervisors:
                task.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary='Verify cleaning task %s' % task.code,
                )
        return True

    def action_approve(self):
        self._check_supervisor()
        for task in self:
            if task.state != 'verification_pending':
                raise UserError('Only verification-pending tasks can be approved.')
            task.write({
                'state': 'verified',
                'verified_by': self.env.uid,
                'verified_date': fields.Datetime.now(),
            })
            if task.zone_id:
                task.zone_id.status = 'clean'
            task.message_post(body='Task verified/approved.')
            if task.staff_id.user_id:
                task.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=task.staff_id.user_id.id,
                    summary='Task %s approved' % task.code,
                )
        return True

    def action_reject(self, reason=None, comment=None):
        self._check_supervisor()
        for task in self:
            if task.state != 'verification_pending':
                raise UserError('Only verification-pending tasks can be rejected.')
            if not reason and not task.reject_reason:
                raise ValidationError('Rejection reason is required.')
            vals = {
                'state': 'rework',
                'reject_reason': reason or task.reject_reason,
                'supervisor_comment': comment or task.supervisor_comment,
            }
            task.write(vals)
            if task.zone_id:
                task.zone_id.status = 'required'
            task.message_post(body='Task rejected for rework. Reason: %s' % (task.reject_reason or ''))
            if task.staff_id.user_id:
                task.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=task.staff_id.user_id.id,
                    summary='Task %s needs rework' % task.code,
                )
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def _check_supervisor(self):
        if not (
            self.env.user.has_group('housekeeping_management.group_hk_supervisor')
            or self.env.user.has_group('housekeeping_management.group_hk_manager')
            or self.env.user.has_group('base.group_system')
        ):
            raise AccessError('Only supervisors or managers can verify tasks.')
