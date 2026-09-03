# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    # ------------------------------------------------------------------
    # Read side: everything the kiosk screen needs, in one call
    # ------------------------------------------------------------------
    def _dw_shopfloor_material_vals(self, move):
        # ``quantity`` on a move line is pre-filled with the *reserved*
        # amount as soon as stock is available, before anyone confirms
        # anything actually got taken — ``picked`` is what means "an
        # operator confirmed this quantity was really consumed". Only
        # picked lines count as "done" here, or every material would show
        # as fully consumed the moment the order is merely reserved.
        picked_lines = move.move_line_ids.filtered('picked')
        done = sum(picked_lines.mapped('quantity'))
        return {
            'move_id': move.id,
            'product_id': move.product_id.id,
            'product_name': move.product_id.display_name,
            'tracking': move.product_id.tracking,
            'uom_name': move.product_uom.name,
            'quantity_needed': move.product_uom_qty,
            'quantity_done': done,
            'is_done': float_compare(done, move.product_uom_qty, precision_rounding=move.product_uom.rounding) >= 0,
            'lots': [{
                'move_line_id': ml.id,
                'lot_name': ml.lot_id.name or ml.lot_name or '',
                'quantity': ml.quantity,
            } for ml in picked_lines if ml.lot_id or ml.lot_name],
        }

    def dw_shopfloor_get_data(self):
        self.ensure_one()
        materials = [
            self._dw_shopfloor_material_vals(m)
            for m in self.move_raw_ids
            if m.state not in ('cancel',)
        ]
        return {
            'id': self.id,
            'name': self.name,
            'production_name': self.production_id.name,
            'product_name': self.product_id.display_name,
            'product_tracking': self.product_tracking,
            'qty_production': self.qty_production,
            'qty_producing': self.qty_producing,
            'qty_produced': self.qty_produced,
            'uom_name': self.product_uom_id.name,
            'state': self.state,
            'working_state': self.workcenter_id.working_state,
            'duration_expected': self.duration_expected,
            'duration': self.duration,
            'date_start': self.date_start and fields.Datetime.to_string(self.date_start),
            'is_user_working': self.is_user_working,
            'finished_lot_name': self.finished_lot_id.name or '',
            'requires_finished_lot': self.product_tracking in ('lot', 'serial'),
            'operation_id': self.operation_id.id,
            'operation_note': self.operation_note or '',
            'has_worksheet': self.has_worksheet,
            'worksheet_type': self.worksheet_type,
            'worksheet_google_slide': self.worksheet_google_slide or '',
            'materials': materials,
        }

    @api.model
    def dw_shopfloor_get_queue(self, workcenter_id):
        """The work orders an operator should see for one work center's
        kiosk screen: ready or already in progress, in the order they
        should be worked on."""
        workorders = self.search([
            ('workcenter_id', '=', workcenter_id),
            ('state', 'in', ('ready', 'progress')),
        ], order='sequence, date_start, id')
        return [{
            'id': wo.id,
            'name': wo.name,
            'production_name': wo.production_id.name,
            'product_name': wo.product_id.display_name,
            'qty_production': wo.qty_production,
            'uom_name': wo.product_uom_id.name,
            'state': wo.state,
            'is_user_working': wo.is_user_working,
        } for wo in workorders]

    # ------------------------------------------------------------------
    # Write side: start/pause/finish are already native (button_start /
    # button_pending / button_finish) — called directly from the client,
    # nothing to wrap here. Below is what's genuinely new for the kiosk.
    # ------------------------------------------------------------------
    def dw_shopfloor_set_qty_producing(self, qty_producing):
        self.ensure_one()
        if qty_producing < 0:
            raise UserError(self.env._("La cantidad no puede ser negativa."))
        self.qty_producing = qty_producing
        return self.dw_shopfloor_get_data()

    def dw_shopfloor_set_finished_lot(self, barcode):
        """Set (creating it if needed) the lot/serial of the product this
        work order is producing — same field (``finished_lot_id``) the
        regular Manufacturing Order form already uses."""
        self.ensure_one()
        barcode = (barcode or '').strip()
        if not barcode:
            raise UserError(self.env._("Escaneá o escribí un número de lote/serie."))
        lot = self.env['stock.lot'].search([
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.company_id.id),
            ('name', '=', barcode),
        ], limit=1)
        if not lot:
            if self.product_tracking == 'serial':
                existing = self.env['stock.move.line'].search_count([
                    ('lot_id.name', '=', barcode), ('lot_id.product_id', '=', self.product_id.id),
                ])
                if existing:
                    raise UserError(self.env._(
                        "El número de serie '%s' ya se usó — cada unidad necesita uno distinto.") % barcode)
            lot = self.env['stock.lot'].create({
                'name': barcode, 'product_id': self.product_id.id, 'company_id': self.company_id.id,
            })
        self.finished_lot_id = lot.id
        return self.dw_shopfloor_get_data()

    def dw_shopfloor_scan_component(self, move_id, barcode):
        """Assign a lot/serial to a raw material move by scanning it — for a
        'serial' product this adds exactly one unit per scan (re-scan for
        more); for a 'lot' product it fills in whatever quantity is still
        missing on that move under this one lot, since one lot commonly
        covers the whole need. Text-match only: no GS1/EPC parsing.
        """
        self.ensure_one()
        move = self.move_raw_ids.filtered(lambda m: m.id == move_id)
        if not move:
            raise UserError(self.env._("No se encontró ese material en esta orden de trabajo."))
        move.ensure_one()
        barcode = (barcode or '').strip()
        if not barcode:
            raise UserError(self.env._("Escaneá o escribí un número de lote/serie."))
        if move.product_id.tracking == 'none':
            raise UserError(self.env._("'%s' no está configurado con seguimiento por lote/serie.")
                             % move.product_id.display_name)

        picked_lines = move.move_line_ids.filtered('picked')
        already_done = sum(picked_lines.mapped('quantity'))
        remaining = move.product_uom_qty - already_done
        if float_compare(remaining, 0, precision_rounding=move.product_uom.rounding) <= 0:
            raise UserError(self.env._("Ya se registró toda la cantidad necesaria de '%s'.")
                             % move.product_id.display_name)

        lot = self.env['stock.lot'].search([
            ('product_id', '=', move.product_id.id),
            ('company_id', '=', move.company_id.id),
            ('name', '=', barcode),
        ], limit=1)
        if not lot:
            lot = self.env['stock.lot'].create({
                'name': barcode, 'product_id': move.product_id.id, 'company_id': move.company_id.id,
            })

        qty_to_add = 1.0 if move.product_id.tracking == 'serial' else remaining
        qty_to_add = min(qty_to_add, remaining)

        # Reuse a reserved-but-not-yet-picked line (created by stock
        # reservation before any specific lot was chosen) instead of piling
        # up a redundant extra line next to it.
        reusable = move.move_line_ids.filtered(lambda ml: not ml.picked and not ml.lot_id)[:1]
        if reusable:
            reusable.write({'lot_id': lot.id, 'quantity': qty_to_add, 'picked': True})
        else:
            existing_picked = picked_lines.filtered(lambda ml: ml.lot_id == lot)[:1]
            if existing_picked and move.product_id.tracking != 'serial':
                existing_picked.quantity += qty_to_add
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'lot_id': lot.id,
                    'quantity': qty_to_add,
                    'picked': True,
                })
        return self.dw_shopfloor_get_data()

    def dw_shopfloor_mark_component_done(self, move_id):
        """For an untracked component: mark its full needed quantity as
        consumed in one tap, using Odoo's own ``_set_quantity_done`` so the
        move lines it creates follow the exact same logic as everywhere
        else in Odoo (reservations included)."""
        self.ensure_one()
        move = self.move_raw_ids.filtered(lambda m: m.id == move_id)
        if not move:
            raise UserError(self.env._("No se encontró ese material en esta orden de trabajo."))
        move.ensure_one()
        if move.product_id.tracking != 'none':
            raise UserError(self.env._("'%s' necesita escanear un lote/serie.") % move.product_id.display_name)
        move._set_quantity_done(move.product_uom_qty)
        move.picked = True
        return self.dw_shopfloor_get_data()

    def dw_shopfloor_remove_move_line(self, move_line_id):
        self.ensure_one()
        line = self.env['stock.move.line'].browse(move_line_id)
        if line.move_id not in self.move_raw_ids:
            raise UserError(self.env._("Esa línea no pertenece a esta orden de trabajo."))
        line.unlink()
        return self.dw_shopfloor_get_data()
