import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

export const AM_NAV = [
    { id: "dashboard", label: "Dashboard", icon: "fa-th-large", xmlid: "fms_asset_management.action_am_dashboard_ui", tag: "fms_asset_management.action_dashboard" },
    { id: "register", label: "Asset Register", icon: "fa-list", xmlid: "fms_asset_management.action_am_register_ui", tag: "fms_asset_management.action_register" },
    { id: "registration", label: "Register Asset", icon: "fa-plus-circle", xmlid: "fms_asset_management.action_am_registration_ui", tag: "fms_asset_management.action_registration", hideReadOnly: true },
    { id: "operations", label: "Operations", icon: "fa-random", xmlid: "fms_asset_management.action_am_operations_ui", tag: "fms_asset_management.action_operations" },
    { id: "qr", label: "QR / Barcode", icon: "fa-qrcode", xmlid: "fms_asset_management.action_am_qr_ui", tag: "fms_asset_management.action_qr" },
];

const NAV_TITLE = Object.fromEntries(AM_NAV.map((item) => [item.id, item.label]));

export class AmAppShell extends Component {
    static template = "fms_asset_management.AmAppShell";
    static props = {
        active: String,
        title: { type: String, optional: true },
        slots: { type: Object, optional: true },
    };

    setup() {
        this.action = useService("action");
        this.state = useState({
            roleLabel: "User",
            isAuditor: false,
            canRegister: false,
            searchQuery: "",
        });
        onWillStart(async () => {
            const [isAdmin, isManager, isAuditor] = await Promise.all([
                user.hasGroup("fms_asset_management.group_asset_administrator"),
                user.hasGroup("fms_asset_management.group_asset_manager"),
                user.hasGroup("fms_asset_management.group_asset_auditor"),
            ]);
            this.state.isAuditor = isAuditor && !isAdmin && !isManager;
            this.state.canRegister = isAdmin || isManager;
            if (isAdmin) {
                this.state.roleLabel = "Asset Administrator";
            } else if (isManager) {
                this.state.roleLabel = "Asset Manager";
            } else if (await user.hasGroup("fms_asset_management.group_asset_finance")) {
                this.state.roleLabel = "Finance User";
            } else if (isAuditor) {
                this.state.roleLabel = "Auditor";
            } else if (await user.hasGroup("fms_asset_management.group_asset_facility_manager")) {
                this.state.roleLabel = "Facility Manager";
            } else if (await user.hasGroup("fms_asset_management.group_asset_technician")) {
                this.state.roleLabel = "Technician";
            }
        });
    }

    get pageTitle() {
        return this.props.title || NAV_TITLE[this.props.active] || "Asset Management";
    }

    get avatarUrl() {
        return `/web/image/res.users/${user.userId}/avatar_128`;
    }

    get userName() {
        return user.name || "User";
    }

    get nav() {
        return AM_NAV.filter((item) => {
            if (item.hideReadOnly && this.state.isAuditor) {
                return false;
            }
            if (item.id === "registration" && !this.state.canRegister) {
                return false;
            }
            return true;
        });
    }

    open(item) {
        if (item.id === this.props.active) {
            return;
        }
        this.action.doAction(item.xmlid, { clearBreadcrumbs: true, forceLeave: true });
    }

    openConfiguration() {
        this.action.doAction("fms_asset_management.action_fms_asset_classification", { clearBreadcrumbs: false });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        const term = (this.state.searchQuery || "").trim();
        this.action.doAction("fms_asset_management.action_am_register_ui", {
            clearBreadcrumbs: true,
            additionalContext: term ? { am_search: term } : {},
        });
    }
}