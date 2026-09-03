/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { Layout } from "@web/search/layout";
import { getDefaultConfig } from "@web/views/view";
import { _t } from "@web/core/l10n/translation";

import { Component, useState, useSubEnv, onWillStart, onWillUnmount } from "@odoo/owl";

/**
 * The Shop Floor kiosk: a touch-first screen for operators, built on top of
 * Community's ``mrp.workorder`` exactly as it ships (button_start /
 * button_pending / button_finish, work center blocking, time tracking) —
 * no parallel execution engine, just a screen for it.
 *
 * Three simple screens, no routing library: pick a work center, pick a
 * work order from its queue, work on it.
 */
class DwMrpShopfloorKiosk extends Component {
    static template = "dw_mrp_shopfloor.Kiosk";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        useSetupAction();
        useSubEnv({
            config: {
                ...getDefaultConfig(),
                ...this.env.config,
            },
        });

        this.state = useState({
            screen: "workcenters", // 'workcenters' | 'queue' | 'workorder'
            loading: true,
            workcenters: [],
            currentWorkcenterId: false,
            queue: [],
            workorder: false, // full dw_shopfloor_get_data() payload
            scanValueLot: "",
            scanValueMaterial: "",
            selectedMaterialMoveId: false,
            activeTab: "materials", // 'materials' | 'instructions'
            blockReasons: [],
            showBlockPanel: false,
            blockReasonId: false,
            blockDescription: "",
            elapsedSeconds: 0,
            busy: false,
        });

        this._timer = null;
        this._workOrderStartedAt = null;

        onWillStart(() => this.loadWorkcenters());
        onWillUnmount(() => this._stopTimer());
    }

    // ------------------------------------------------------------------
    // Navigation / loading
    // ------------------------------------------------------------------
    async loadWorkcenters() {
        this.state.loading = true;
        this.state.workcenters = await this.orm.call("mrp.workcenter", "dw_shopfloor_get_workcenters", []);
        this.state.loading = false;
    }

    async openWorkcenter(workcenterId) {
        this.state.currentWorkcenterId = workcenterId;
        this.state.loading = true;
        this.state.queue = await this.orm.call("mrp.workorder", "dw_shopfloor_get_queue", [workcenterId]);
        this.state.loading = false;
        this.state.screen = "queue";
    }

    async openWorkorder(workorderId) {
        this.state.loading = true;
        const data = await this.orm.call("mrp.workorder", "dw_shopfloor_get_data", [workorderId]);
        this._applyWorkorderData(data);
        this.state.activeTab = "materials";
        this.state.selectedMaterialMoveId = false;
        this.state.scanValueMaterial = "";
        this.state.scanValueLot = "";
        this.state.screen = "workorder";
        this.state.loading = false;
    }

    async backToQueue() {
        this._stopTimer();
        this.state.workorder = false;
        await this.openWorkcenter(this.state.currentWorkcenterId);
    }

    backToWorkcenters() {
        this._stopTimer();
        this.state.screen = "workcenters";
        this.state.workorder = false;
        this.loadWorkcenters();
    }

    _applyWorkorderData(data) {
        this.state.workorder = data;
        this._stopTimer();
        // ``state`` stays 'progress' across a pause (native Odoo: 'pending'
        // means "waiting for another work order", not "the operator paused
        // this one") — ``is_user_working`` is the real "is the clock
        // ticking right now" signal, backed by an open time log entry.
        if (data.is_user_working && data.date_start) {
            // Ticks from the order's original start time — resuming after a
            // pause doesn't move date_start forward while state stays
            // 'progress', so this reads as "total elapsed since it began".
            // The authoritative accumulated duration (which does exclude
            // paused gaps) is ``data.duration``, refreshed from the server
            // on every reload and shown alongside this clock.
            this._workOrderStartedAt = new Date(data.date_start.replace(" ", "T") + "Z").getTime();
            this._tick();
            this._timer = setInterval(() => this._tick(), 1000);
        } else {
            this.state.elapsedSeconds = 0;
        }
    }

    _tick() {
        if (!this._workOrderStartedAt) {
            return;
        }
        this.state.elapsedSeconds = Math.max(0, Math.floor((Date.now() - this._workOrderStartedAt) / 1000));
    }

    _stopTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
        this._workOrderStartedAt = null;
    }

    formatElapsed(totalSeconds) {
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        const pad = (n) => String(n).padStart(2, "0");
        return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
    }

    // ------------------------------------------------------------------
    // Work order actions
    // ------------------------------------------------------------------
    async _reloadWorkorder() {
        const data = await this.orm.call("mrp.workorder", "dw_shopfloor_get_data", [this.state.workorder.id]);
        this._applyWorkorderData(data);
    }

    async runGuarded(fn) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await fn();
        } finally {
            this.state.busy = false;
        }
    }

    onStart() {
        return this.runGuarded(async () => {
            await this.orm.call("mrp.workorder", "button_start", [this.state.workorder.id]);
            await this._reloadWorkorder();
        });
    }

    onPause() {
        return this.runGuarded(async () => {
            await this.orm.call("mrp.workorder", "button_pending", [this.state.workorder.id]);
            await this._reloadWorkorder();
        });
    }

    async onFinish() {
        if (this.state.workorder.requires_finished_lot && !this.state.workorder.finished_lot_name) {
            this.notification.add(
                _t("Escaneá o escribí el lote/serie del producto antes de finalizar."),
                { type: "warning" }
            );
            return;
        }
        return this.runGuarded(async () => {
            await this.orm.call("mrp.workorder", "button_finish", [this.state.workorder.id]);
            this.notification.add(_t("Orden de trabajo finalizada."), { type: "success" });
            await this.backToQueue();
        });
    }

    onQtyProducingChange(ev) {
        const qty = parseFloat(ev.target.value);
        if (isNaN(qty)) {
            return;
        }
        return this.runGuarded(async () => {
            const data = await this.orm.call(
                "mrp.workorder", "dw_shopfloor_set_qty_producing", [this.state.workorder.id, qty]
            );
            this._applyWorkorderData(data);
        });
    }

    async onScanFinishedLot() {
        const barcode = this.state.scanValueLot.trim();
        if (!barcode) {
            return;
        }
        this.state.scanValueLot = "";
        return this.runGuarded(async () => {
            const data = await this.orm.call(
                "mrp.workorder", "dw_shopfloor_set_finished_lot", [this.state.workorder.id, barcode]
            );
            this._applyWorkorderData(data);
        });
    }

    selectMaterial(moveId) {
        this.state.selectedMaterialMoveId = moveId;
        this.state.scanValueMaterial = "";
    }

    async onScanComponent() {
        const moveId = this.state.selectedMaterialMoveId;
        const barcode = this.state.scanValueMaterial.trim();
        if (!moveId || !barcode) {
            return;
        }
        this.state.scanValueMaterial = "";
        return this.runGuarded(async () => {
            const data = await this.orm.call(
                "mrp.workorder", "dw_shopfloor_scan_component", [this.state.workorder.id, moveId, barcode]
            );
            this._applyWorkorderData(data);
        });
    }

    onMarkComponentDone(moveId) {
        return this.runGuarded(async () => {
            const data = await this.orm.call(
                "mrp.workorder", "dw_shopfloor_mark_component_done", [this.state.workorder.id, moveId]
            );
            this._applyWorkorderData(data);
        });
    }

    onRemoveMoveLine(moveLineId) {
        return this.runGuarded(async () => {
            const data = await this.orm.call(
                "mrp.workorder", "dw_shopfloor_remove_move_line", [this.state.workorder.id, moveLineId]
            );
            this._applyWorkorderData(data);
        });
    }

    worksheetPdfUrl() {
        if (!this.state.workorder || !this.state.workorder.operation_id) {
            return "";
        }
        return `/web/content/mrp.routing.workcenter/${this.state.workorder.operation_id}/worksheet`;
    }

    // ------------------------------------------------------------------
    // Block / unblock work center
    // ------------------------------------------------------------------
    async openBlockPanel() {
        this.state.blockReasons = await this.orm.call(
            "mrp.workcenter", "dw_shopfloor_get_block_reasons", [this.state.currentWorkcenterId]
        );
        this.state.blockReasonId = this.state.blockReasons[0] ? this.state.blockReasons[0].id : false;
        this.state.blockDescription = "";
        this.state.showBlockPanel = true;
    }

    closeBlockPanel() {
        this.state.showBlockPanel = false;
    }

    onSelectBlockReason(ev) {
        this.state.blockReasonId = parseInt(ev.target.value, 10);
    }

    onBlockDescriptionChange(ev) {
        this.state.blockDescription = ev.target.value;
    }

    confirmBlock() {
        return this.runGuarded(async () => {
            await this.orm.call("mrp.workcenter", "dw_shopfloor_block", [
                this.state.currentWorkcenterId, this.state.blockReasonId, this.state.blockDescription,
            ]);
            this.state.showBlockPanel = false;
            if (this.state.screen === "workorder") {
                await this._reloadWorkorder();
            } else {
                await this.loadWorkcenters();
            }
        });
    }

    unblockWorkcenter() {
        return this.runGuarded(async () => {
            await this.orm.call("mrp.workcenter", "dw_shopfloor_unblock", [this.state.currentWorkcenterId]);
            if (this.state.screen === "workorder") {
                await this._reloadWorkorder();
            } else {
                await this.loadWorkcenters();
            }
        });
    }
}

registry.category("actions").add("dw_mrp_shopfloor_kiosk", DwMrpShopfloorKiosk);
