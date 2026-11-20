import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { registry } from "@web/core/registry";
import { AmAppShell } from "@fms_asset_management/owl/ui/am_shell";
import { AM_COMPONENTS } from "@fms_asset_management/owl/ui/am_ui";

const MODEL = "maintenance.equipment";
const PAGE_SIZE = 20;
const FIELDS = [
    "fms_asset_code",
    "name",
    "fms_lifecycle_state",
    "fms_condition",
    "fms_health_status",
    "fms_classification_id",
    "fms_location_id",
    "serial_no",
    "fms_book_value",
];

export class AssetRegister extends Component {
    static template = "fms_asset_management.Register";
    static components = { AmAppShell, ...AM_COMPONENTS };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: "",
            rows: [],
            total: 0,
            offset: 0,
            search: "",
            lifecycle: "",
            canCreate: false,
            classFilter: "",
            classOptions: [],
        });
        onWillStart(async () => {
            const ctx = this.props.action?.context || {};
            if (ctx.am_search) {
                this.state.search = String(ctx.am_search);
            }
            this.state.classOptions = await this.orm.searchRead(
                "fms.asset.classification",
                [["level", "=", "subtype"], ["active", "=", true]],
                ["id", "complete_name"],
                { order: "complete_name", limit: 200 }
            );
            await this.reload();
        });
    }

    async buildDomain() {
        return this.orm.call(MODEL, "fms_get_register_domain", [
            this.state.search,
            this.state.lifecycle || false,
            this.state.classFilter ? parseInt(this.state.classFilter, 10) : false,
            false,
        ]);
    }

    async reload() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const domain = await this.buildDomain();
            const [rows, total] = await Promise.all([
                this.orm.searchRead(MODEL, domain, FIELDS, {
                    order: "fms_asset_code desc, id desc",
                    limit: PAGE_SIZE,
                    offset: this.state.offset,
                }),
                this.orm.searchCount(MODEL, domain),
            ]);
            this.state.rows = rows;
            this.state.total = total;
            this.state.canCreate = await user.checkAccessRight(MODEL, "create");
        } catch (error) {
            this.state.rows = [];
            this.state.error = error?.data?.message || error?.message || "Could not load assets.";
        } finally {
            this.state.loading = false;
        }
    }

    async onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.offset = 0;
        await this.reload();
    }

    async onLifecycleChange(ev) {
        this.state.lifecycle = ev.target.value;
        this.state.offset = 0;
        await this.reload();
    }

    async onClassChange(ev) {
        this.state.classFilter = ev.target.value;
        this.state.offset = 0;
        await this.reload();
    }

    async nextPage() {
        if (this.state.offset + PAGE_SIZE < this.state.total) {
            this.state.offset += PAGE_SIZE;
            await this.reload();
        }
    }

    async prevPage() {
        if (this.state.offset >= PAGE_SIZE) {
            this.state.offset -= PAGE_SIZE;
            await this.reload();
        }
    }

    openDetail(recordId) {
        this.action.doAction("fms_asset_management.action_am_detail_ui", {
            additionalContext: { fms_equipment_id: recordId },
            clearBreadcrumbs: true,
        });
    }

    openRegistration() {
        this.action.doAction("fms_asset_management.action_am_registration_ui", { clearBreadcrumbs: true });
    }

    displayRelation(value) {
        if (Array.isArray(value)) {
            return value[1] || "";
        }
        return "";
    }

    get pageLabel() {
        const from = this.state.total ? this.state.offset + 1 : 0;
        const to = Math.min(this.state.offset + PAGE_SIZE, this.state.total);
        return `${from}-${to} of ${this.state.total}`;
    }
}

registry.category("actions").add("fms_asset_management.action_register", AssetRegister);