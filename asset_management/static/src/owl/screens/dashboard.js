import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { registry } from "@web/core/registry";
import { AmAppShell } from "@fms_asset_management/owl/ui/am_shell";
import { AM_COMPONENTS } from "@fms_asset_management/owl/ui/am_ui";

export class AssetDashboard extends Component {
    static template = "fms_asset_management.Dashboard";
    static components = { AmAppShell, ...AM_COMPONENTS };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, error: "", data: null, canRegister: false });
        onWillStart(async () => {
            const [isAdmin, isManager] = await Promise.all([
                user.hasGroup("fms_asset_management.group_asset_administrator"),
                user.hasGroup("fms_asset_management.group_asset_manager"),
            ]);
            this.state.canRegister = isAdmin || isManager;
            await this.reload();
        });
    }

    async reload() {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.data = await this.orm.call("fms.asset.dashboard", "get_dashboard_data", []);
        } catch (error) {
            this.state.data = null;
            this.state.error = error?.data?.message || error?.message || "Could not load dashboard data.";
        } finally {
            this.state.loading = false;
        }
    }

    get data() {
        return (
            this.state.data || {
                available: false,
                lifecycle_counts: {},
                recent_assets: [],
            }
        );
    }

    kpiTone(flag) {
        return flag ? "warning" : "";
    }

    kpiToneDanger(flag) {
        return flag ? "danger" : "";
    }

    get lifecycleRows() {
        const counts = this.data.lifecycle_counts || {};
        return Object.keys(counts)
            .sort()
            .map((key) => ({ state: key, count: counts[key] }));
    }

    get attentionCount() {
        return (
            (this.data.pending_transfers || 0) +
            (this.data.pending_disposals || 0) +
            (this.data.warranty_expiring || 0) +
            (this.data.depreciation_due_count || 0)
        );
    }

    get attentionMessage() {
        return `${this.attentionCount} pending workflow or contract items — review Operations and finance KPIs.`;
    }

    get dashboardUnavailableReason() {
        return this.data.reason || "You do not have access to asset records.";
    }

    openNav(xmlid) {
        this.action.doAction(xmlid, { clearBreadcrumbs: true });
    }

    openRegister() {
        this.openNav("fms_asset_management.action_am_register_ui");
    }

    openRegistration() {
        this.openNav("fms_asset_management.action_am_registration_ui");
    }

    openOperations() {
        this.openNav("fms_asset_management.action_am_operations_ui");
    }

    openQr() {
        this.openNav("fms_asset_management.action_am_qr_ui");
    }

    openDetail(recordId) {
        this.action.doAction("fms_asset_management.action_am_detail_ui", {
            additionalContext: { fms_equipment_id: recordId },
            clearBreadcrumbs: true,
        });
    }

    formatMoney(value) {
        const num = Number(value || 0);
        return num.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
}

registry.category("actions").add("fms_asset_management.action_dashboard", AssetDashboard);