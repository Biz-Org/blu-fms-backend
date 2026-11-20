import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { AmAppShell } from "@fms_asset_management/owl/ui/am_shell";

const STEPS = ["basic", "location", "purchase", "financial", "documents", "review"];
const STEP_LABELS = {
    basic: "Basic Information",
    location: "Location",
    purchase: "Purchase / Acquisition",
    financial: "Financial Information",
    documents: "Documents",
    review: "Review",
};

export class AssetRegistration extends Component {
    static template = "fms_asset_management.Registration";
    static components = { AmAppShell };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            stepIndex: 0,
            loading: false,
            saving: false,
            classifications: [],
            locations: [],
            form: this.emptyForm(),
        });
        onWillStart(async () => {
            const [classifications, locations] = await Promise.all([
                this.orm.searchRead(
                    "fms.asset.classification",
                    [["level", "=", "subtype"], ["active", "=", true]],
                    ["id", "complete_name"],
                    { order: "complete_name" }
                ),
                this.orm.searchRead(
                    "fms.asset.location",
                    [["location_type", "=", "room"], ["active", "=", true]],
                    ["id", "complete_name"],
                    { order: "complete_name" }
                ),
            ]);
            this.state.classifications = classifications;
            this.state.locations = locations;
        });
    }

    emptyForm() {
        return {
            name: "",
            fms_classification_id: "",
            model: "",
            serial_no: "",
            fms_manufacturer: "",
            note: "",
            fms_location_id: "",
            fms_acquisition_date: "",
            partner_id: "",
            fms_purchase_order_ref: "",
            fms_invoice_ref: "",
            cost: "",
            fms_residual_value: "",
            fms_useful_life_months: "",
            fms_depreciation_method: "",
            fms_condition: "good",
            attachment_description: "",
            fms_confirm_active: true,
        };
    }

    get stepKey() {
        return STEPS[this.state.stepIndex];
    }

    get stepLabel() {
        return STEP_LABELS[this.stepKey];
    }

    nextStep() {
        if (this.stepKey === "basic" && !this.state.form.name.trim()) {
            this.notification.add("Asset name is required.", { type: "danger" });
            return;
        }
        if (this.state.stepIndex < STEPS.length - 1) {
            this.state.stepIndex += 1;
        }
    }

    prevStep() {
        if (this.state.stepIndex > 0) {
            this.state.stepIndex -= 1;
        }
    }

    async submitRegistration() {
        if (!this.state.form.name.trim()) {
            this.notification.add("Asset name is required.", { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            const payload = { ...this.state.form, fms_lifecycle_state: this.state.form.fms_confirm_active ? "active" : "draft" };
            const created = await this.orm.call(
                "fms.asset.registration.wizard",
                "fms_register_asset",
                [payload]
            );
            this.notification.add(`Asset ${created.fms_asset_code} created.`, { type: "success" });
            this.action.doAction("fms_asset_management.action_am_detail_ui", {
                additionalContext: { fms_equipment_id: created.id },
                clearBreadcrumbs: true,
            });
        } catch (error) {
            this.notification.add(error?.data?.message || error?.message || "Registration failed.", { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    openRegister() {
        this.action.doAction("fms_asset_management.action_am_register_ui", { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("fms_asset_management.action_registration", AssetRegistration);