import { Component } from "@odoo/owl";

export class AmKpiCard extends Component {
    static template = "fms_asset_management.AmKpiCard";
    static props = {
        label: String,
        value: { type: [Number, String] },
        icon: { type: String, optional: true },
        tone: { type: String, optional: true },
        hint: { type: String, optional: true },
        onClick: { type: Function, optional: true },
    };
    onClick() {
        this.props.onClick?.();
    }
}

export class AmStatusBadge extends Component {
    static template = "fms_asset_management.AmStatusBadge";
    static props = {
        state: { type: String, optional: true },
        label: { type: String, optional: true },
    };
    get tone() {
        const state = this.props.state || "";
        if (["active", "completed", "healthy", "good", "excellent", "running", "posted", "approved"].includes(state)) {
            return "success";
        }
        if (["disposed", "critical", "poor", "degraded", "expired", "rejected"].includes(state)) {
            return "danger";
        }
        if (
            [
                "under_maintenance",
                "attention",
                "fair",
                "warning",
                "draft",
                "submitted",
                "expiring",
                "pending",
            ].includes(state)
        ) {
            return "warning";
        }
        return "muted";
    }
    get text() {
        return this.props.label || (this.props.state || "").replace(/_/g, " ");
    }
}

export class AmEmptyState extends Component {
    static template = "fms_asset_management.AmEmptyState";
    static props = {
        title: String,
        hint: { type: String, optional: true },
        icon: { type: String, optional: true },
    };
}

export class AmAlertBanner extends Component {
    static template = "fms_asset_management.AmAlertBanner";
    static props = {
        title: String,
        message: { type: String, optional: true },
        tone: { type: String, optional: true },
        actionLabel: { type: String, optional: true },
        onAction: { type: Function, optional: true },
    };
    onAction() {
        this.props.onAction?.();
    }
}

export const AM_COMPONENTS = {
    AmKpiCard,
    AmStatusBadge,
    AmEmptyState,
    AmAlertBanner,
};