# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    @api.model
    def dw_shopfloor_get_workcenters(self):
        """List of work centers for the Shop Floor kiosk's picker screen,
        with the counts operators care about — everything here is already
        native Odoo (``workorder_ready_count``/``workorder_progress_count``),
        just packaged for the kiosk in one call."""
        workcenters = self.search([])
        return [{
            'id': wc.id,
            'name': wc.display_name,
            'working_state': wc.working_state,
            'ready_count': wc.workorder_ready_count,
            'progress_count': wc.workorder_progress_count,
        } for wc in workcenters]

    def dw_shopfloor_get_block_reasons(self):
        """Blocking reasons an operator can pick from — the same
        ``mrp.workcenter.productivity.loss`` records (``manual=True``) the
        standard 'Block Workcenter' wizard already uses."""
        reasons = self.env['mrp.workcenter.productivity.loss'].search([('manual', '=', True)])
        return [{'id': r.id, 'name': r.name} for r in reasons]

    def dw_shopfloor_block(self, loss_id, description=False):
        """Block this work center with a reason, the same way the native
        'Block Workcenter' wizard does (``mrp.workcenter.productivity`` +
        ``button_block``) — just skipping the extra dialog for speed on a
        touch screen."""
        self.ensure_one()
        if self.working_state == 'blocked':
            raise UserError(self.env._("Este centro de trabajo ya está bloqueado."))
        productivity = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.id,
            'loss_id': loss_id,
            'description': description or '',
        })
        productivity.button_block()
        return True

    def dw_shopfloor_unblock(self):
        self.ensure_one()
        return self.unblock()
