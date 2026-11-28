from odoo import api, fields, models


class HkChecklistTemplate(models.Model):
    _name = 'hk.checklist.template'
    _description = 'Checklist Template'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    item_ids = fields.One2many('hk.checklist.item', 'template_id')
    item_count = fields.Integer(compute='_compute_item_count')

    @api.depends('item_ids')
    def _compute_item_count(self):
        for template in self:
            template.item_count = len(template.item_ids)


class HkChecklistItem(models.Model):
    _name = 'hk.checklist.item'
    _description = 'Checklist Template Item'
    _order = 'sequence, id'

    template_id = fields.Many2one('hk.checklist.template', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    section = fields.Selection(
        [('pre', 'Pre-Cleaning'), ('cleaning', 'Cleaning'), ('post', 'Post-Cleaning')],
        default='cleaning',
        required=True,
    )
    sequence = fields.Integer(default=10)
    is_mandatory = fields.Boolean(default=True)
    instructions = fields.Text()


class HkTaskChecklistLine(models.Model):
    _name = 'hk.task.checklist.line'
    _description = 'Task Checklist Line'
    _order = 'sequence, id'

    task_id = fields.Many2one('hk.task', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True)
    section = fields.Selection(
        [('pre', 'Pre-Cleaning'), ('cleaning', 'Cleaning'), ('post', 'Post-Cleaning')],
        default='cleaning',
        required=True,
    )
    sequence = fields.Integer(default=10)
    is_mandatory = fields.Boolean(default=True)
    is_done = fields.Boolean(string='Completed')
    is_na = fields.Boolean(string='Not Applicable')
    instructions = fields.Text()
    remarks = fields.Char()

    def action_toggle_done(self):
        for line in self:
            line.is_done = not line.is_done
            if line.is_done:
                line.is_na = False
        return True
