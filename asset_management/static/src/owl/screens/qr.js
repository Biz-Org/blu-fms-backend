import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { AmAppShell } from "@fms_asset_management/owl/ui/am_shell";

const EQUIPMENT = "maintenance.equipment";

export class AssetQr extends Component {
    static template = "fms_asset_management.Qr";
    static components = { AmAppShell };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            rows: [],
            scanToken: "",
            scanError: "",
        });
        onWillStart(async () => {
            await this.reload();
        });
    }

    async reload() {
        this.state.loading = true;
        try {
            this.state.rows = await this.orm.searchRead(
                EQUIPMENT,
                [],
                ["fms_asset_code", "name", "fms_qr_token", "fms_barcode"],
                { order: "fms_asset_code desc", limit: 50 }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async scanAsset() {
        this.state.scanError = "";
        try {
            const result = await this.orm.call(EQUIPMENT, "fms_resolve_qr_token", [this.state.scanToken.trim()]);
            this.action.doAction("fms_asset_management.action_am_detail_ui", {
                additionalContext: { fms_equipment_id: result.id },
                clearBreadcrumbs: true,
            });
        } catch (error) {
            this.state.scanError = error?.data?.message || error?.message || "No asset found.";
        }
    }

    openDetail(id) {
        this.action.doAction("fms_asset_management.action_am_detail_ui", {
            additionalContext: { fms_equipment_id: id },
            clearBreadcrumbs: true,
        });
    }
}

registry.category("actions").add("fms_asset_management.action_qr", AssetQr);