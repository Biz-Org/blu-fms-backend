import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { registry } from "@web/core/registry";
import { AmAppShell } from "@fms_asset_management/owl/ui/am_shell";

const TRANSFER = "fms.asset.transfer";
const DISPOSAL = "fms.asset.disposal";

export class AssetOperations extends Component {
    static template = "fms_asset_management.Operations";
    static components = { AmAppShell };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            transfers: [],
            disposals: [],
            canApprove: false,
        });
        onWillStart(async () => {
            const [isAdmin, isManager] = await Promise.all([
                user.hasGroup("fms_asset_management.group_asset_administrator"),
                user.hasGroup("fms_asset_management.group_asset_manager"),
            ]);
            this.state.canApprove = isAdmin || isManager;
            await this.reload();
        });
    }

    async reload() {
        this.state.loading = true;
        try {
            const [transfers, disposals] = await Promise.all([
                this.orm.searchRead(TRANSFER, [["state", "in", ["submitted", "approved"]]], ["name", "equipment_id", "state", "scheduled_transfer_date"], { order: "id desc", limit: 30 }),
                this.orm.searchRead(DISPOSAL, [["state", "in", ["submitted", "approved"]]], ["name", "equipment_id", "state", "disposal_date"], { order: "id desc", limit: 30 }),
            ]);
            this.state.transfers = transfers;
            this.state.disposals = disposals;
        } finally {
            this.state.loading = false;
        }
    }

    displayRelation(value) {
        return Array.isArray(value) ? value[1] : "";
    }

    async workflow(recordId, model, method) {
        try {
            await this.orm.call(model, method, [[recordId]]);
            this.notification.add("Workflow updated.", { type: "success" });
            await this.reload();
        } catch (error) {
            this.notification.add(error?.data?.message || error?.message || "Action failed.", { type: "danger" });
        }
    }
}

registry.category("actions").add("fms_asset_management.action_operations", AssetOperations);