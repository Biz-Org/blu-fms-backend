import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { AmAppShell } from "@fms_asset_management/owl/ui/am_shell";
import { AM_COMPONENTS } from "@fms_asset_management/owl/ui/am_ui";

const EQUIPMENT = "maintenance.equipment";
const ASSIGNMENT = "fms.asset.assignment";
const WARRANTY = "fms.asset.warranty";
const AMC = "fms.asset.amc";
const INSPECTION = "fms.asset.inspection";
const TRANSFER = "fms.asset.transfer";
const DISPOSAL = "fms.asset.disposal";
const LOCATION = "fms.asset.location";
const DEPRECIATION = "fms.asset.depreciation.schedule";

export class AssetDetail extends Component {
    static template = "fms_asset_management.Detail";
    static components = { AmAppShell, ...AM_COMPONENTS };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: "",
            tab: "overview",
            data: null,
            equipmentId: false,
            userOptions: [],
            locationOptions: [],
            assignmentForm: {
                assignment_type: "employee",
                assigned_user_id: "",
                department: "",
                assignment_date: "",
                notes: "",
            },
            inspectionForm: {
                name: "Inspection",
                condition: "good",
                health_status: "healthy",
                health_score: "",
                observations: "",
                complete: true,
            },
            transferForm: { to_location_id: "", reason: "", submit: true },
            disposalForm: { disposal_reason: "end_of_life", remarks: "", submit: true },
            warrantyForm: { name: "Warranty", end_date: "" },
            amcForm: { name: "AMC", contract_end_date: "" },
            depreciationForm: { auto_generate: true },
            saving: false,
        });
        onWillStart(async () => {
            const ctx = this.props.action?.context || {};
            const equipmentId = ctx.fms_equipment_id || ctx.active_id;
            this.state.equipmentId = equipmentId ? parseInt(equipmentId, 10) : false;
            if (!this.state.equipmentId) {
                this.state.loading = false;
                this.state.error = "Open an asset from the Asset Register.";
                return;
            }
            await this.reload();
            await Promise.all([this.loadUsers(""), this.loadLocations("")]);
        });
    }

    async reload() {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.data = await this.orm.call(EQUIPMENT, "fms_get_detail_payload_by_id", [this.state.equipmentId]);
        } catch (error) {
            this.state.data = null;
            this.state.error = error?.data?.message || error?.message || "Could not load asset.";
        } finally {
            this.state.loading = false;
        }
    }

    async loadUsers(term) {
        this.state.userOptions = await this.orm.call(EQUIPMENT, "fms_search_assignable_users", [term || "", 25]);
    }

    async loadLocations(term) {
        this.state.locationOptions = await this.orm.call(LOCATION, "fms_search_locations", [term || "", 40]);
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    displayPair(value) {
        return Array.isArray(value) ? value[1] : value || "—";
    }

    openRegister() {
        this.action.doAction("fms_asset_management.action_am_register_ui", { clearBreadcrumbs: true });
    }

    async withSave(fn) {
        this.state.saving = true;
        try {
            await fn();
            await this.reload();
        } catch (error) {
            this.notification.add(error?.data?.message || error?.message || "Request failed.", { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async submitAssignment() {
        await this.withSave(async () => {
            await this.orm.call(ASSIGNMENT, "fms_create_assignment", [this.state.equipmentId, this.state.assignmentForm]);
            this.notification.add("Assignment recorded.", { type: "success" });
        });
    }

    async submitInspection() {
        await this.withSave(async () => {
            await this.orm.call(INSPECTION, "fms_create_inspection", [this.state.equipmentId, this.state.inspectionForm]);
            this.notification.add("Inspection recorded.", { type: "success" });
        });
    }

    async submitTransfer() {
        await this.withSave(async () => {
            await this.orm.call(TRANSFER, "fms_create_transfer", [this.state.equipmentId, this.state.transferForm]);
            this.notification.add("Transfer submitted.", { type: "success" });
        });
    }

    async submitDisposal() {
        await this.withSave(async () => {
            await this.orm.call(DISPOSAL, "fms_create_disposal", [this.state.equipmentId, this.state.disposalForm]);
            this.notification.add("Disposal submitted.", { type: "success" });
        });
    }

    async submitWarranty() {
        await this.withSave(async () => {
            await this.orm.call(WARRANTY, "fms_create_warranty", [this.state.equipmentId, this.state.warrantyForm]);
            this.notification.add("Warranty saved.", { type: "success" });
        });
    }

    async submitAmc() {
        await this.withSave(async () => {
            await this.orm.call(AMC, "fms_create_amc", [this.state.equipmentId, this.state.amcForm]);
            this.notification.add("AMC saved.", { type: "success" });
        });
    }

    async regenerateQr() {
        await this.withSave(async () => {
            await this.orm.call(EQUIPMENT, "action_fms_regenerate_qr", [[this.state.equipmentId]]);
            this.notification.add("QR token regenerated.", { type: "success" });
        });
    }

    async createDepreciationSchedule() {
        await this.withSave(async () => {
            await this.orm.call(DEPRECIATION, "fms_create_schedule", [
                this.state.equipmentId,
                this.state.depreciationForm,
            ]);
            this.notification.add("Depreciation schedule created.", { type: "success" });
        });
    }

    async postDueDepreciation() {
        const scheduleId = this.state.data?.depreciation?.id;
        if (!scheduleId) {
            return;
        }
        await this.withSave(async () => {
            await this.orm.call(DEPRECIATION, "action_post_due_lines", [[scheduleId]]);
            this.notification.add("Due depreciation periods posted.", { type: "success" });
        });
    }
}

registry.category("actions").add("fms_asset_management.action_detail", AssetDetail);