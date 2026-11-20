# Requirements → Implementation Checklist

Sources:

- `Complaint and Helpdesk Management Functional Scope.docx` (§3–§18)
- `Complaint & Helpdesk Management Screen.pptx` (18 slides; text extraction empty — slides appear image-based; OWL screens mapped to the 15 primary UIs in the Functional Scope)
- Code under `custom_addons/fms_helpdesk` (v18.0.1.10.0)

Legend:

| Status | Meaning |
|---|---|
| **Done (tested)** | Implemented and covered by automated tests in this review |
| **Done (code)** | Implemented in backend/UI; **not** covered by automated UI/browser tests |
| **Partial** | Present but incomplete vs Functional Scope |
| **Missing** | Not implemented |
| **Out of scope** | Owned by another FMS module per §17 |

**Do not treat Partial / Missing / Done (code) as fully verified in production.**

---

## A. 15 Primary Screens

| # | Primary UI | Status | Evidence / notes |
|---|---|---|---|
| 01 | Helpdesk Dashboard | **Done (tested)** KPIs; **Partial** PPT polish | `_screen_dashboard`; analytics tests match DB totals. Quick actions added (Complaints, Work Queue, SLA Breaches, Escalations, Reports, Create). Browser PPT pixel-match **not** re-verified this run. |
| 02 | Complaints / Tickets | **Done (code)** | List + filters + export CSV. Full filter matrix (unit, subcategory, assignee) **Partial**. Lifecycle actions mainly via Ticket Details / modals. |
| 03 | Create Ticket | **Done (tested)** | `save_ticket` / Form tests; preview routing/SLA. Attachment upload in OWL **Done (code)**. |
| 04 | My Complaints | **Done (code)** | Filters by logged-in reporter/resident. Resident feedback-from-this-screen UX **Partial**. |
| 05 | Work Queue | **Done (tested)** tabs | My / Unassigned / Team / Due / Breached / All. **Fixed** Team tab member filter this review. |
| 06 | Assignment Management | **Done (code)** | Assign modal + history KPIs. Controlled **bulk** assignment **Missing**. |
| 07 | Categories Management | **Done (tested)** | Add/edit category + subcategories via modal; Form test. |
| 08 | Routing Rules | **Done (tested)** | CRUD + Test Routing wizard/modal. |
| 09 | Priority & SLA | **Done (code)** | Policies, pause flags, simulator RPC. PPT visual fidelity **not** re-verified. |
| 10 | Escalation Management | **Done (code)** | Needs / at-risk / breached tabs + create/escalate. Prior PPT layout work; not re-browser-tested this run. |
| 11 | Resolution & Closure | **Done (code)** | Resolve / verify / close actions. |
| 12 | Resident Feedback | **Done (code)** | Pending/submitted/reviewed; low-rating filter. Submit-from-OWL for residents **Partial**. |
| 13 | Ticket Details | **Partial → improved** | History, SLA, attachments, Assign/Escalate/Resolve/Verify/Close/Reopen wired. Edit/comment/add-attachment inline still **Partial**. |
| 14 | Reports & Analytics | **Done (tested)** KPIs/CSV | Shared `_sla_breakdown`. Property/building/unit filters, PDF/Excel, rating trends **Partial/Missing**. |
| 15 | Helpdesk Settings | **Done (code)** | Reopen/feedback/attachments exposed this review. Notification preference UI **Missing**. Numbering prefix fixed to HD- (not editable in UI). |

---

## B. Supporting Action UIs (§5)

| Action | Status |
|---|---|
| Create / Edit Ticket | **Done (code)** create; edit **Partial** |
| Assign / Reassign | **Done (code)** modal |
| Add Category / Subcategory | **Done (code)** |
| Create / Edit Routing Rule | **Done (code)** |
| Test Routing | **Done (tested)** |
| Add / Edit SLA Policy | **Done (code)** |
| SLA Simulator | **Done (code)** |
| Escalate Ticket | **Done (code)** |
| Add Resolution | **Done (code)** |
| Verify Resolution | **Done (code)** |
| Close Ticket | **Done (code)** |
| Reopen Ticket | **Done (code)** modal + reason |
| Resident Feedback form | **Partial** (backend + Feedback screen; resident OWL submit incomplete) |
| Attachment upload | **Done (code)** create path |
| Comment / Activity update | **Partial** (history via ORM; dedicated comment UI thin) |

---

## C. Backend Workflows

| Area | Status | Tested? |
|---|---|---|
| Ticket numbering HD-* on submit | **Done (tested)** | Yes |
| Category/subcategory validation | **Done (tested)** | Yes |
| First-match routing + order | **Done (tested)** | Yes |
| Round-robin when no rule | **Done (tested)** | Yes |
| Priority / SLA apply on submit | **Done (tested)** | Yes |
| SLA on track → at risk → breach | **Done (tested)** | Yes |
| SLA pause on waiting states | **Done (tested)** | Yes |
| Auto-escalate on breach when configured | **Done (tested)** | Yes |
| Assignment / reassign + history | **Done (tested)** | Yes |
| Resolution → verify → close → feedback | **Done (tested)** | Yes |
| Reopen window + reason | **Done (tested)** | Yes |
| Protected audit history | **Done (tested)** | Yes |
| SLA cron | **Done (tested)** | Yes |
| Dashboard/report KPI consistency | **Done (tested)** | Yes |

---

## D. Permissions (§11)

| Role | Status | Tested? |
|---|---|---|
| Resident (own tickets, feedback, verify) | **Done (tested)** | Yes |
| Agent (work / resolve; no assign/escalate/close) | **Done (tested)** | Yes |
| Team Lead (assign/escalate/verify/close/reopen) | **Done (tested)** | Yes |
| Manager / Viewer read limits | **Done (tested)** | Yes |
| Admin configure | **Done (tested)** | Yes |
| Company record rules | **Done (code)** | Partial coverage |

---

## E. Notifications (§12)

| Event | Status | Tested? |
|---|---|---|
| SLA At Risk / Breached | **Done (tested)** chatter/activity | Yes (analytics) |
| Escalation assigned | **Done (code)** | Indirect |
| Ticket assigned / status / feedback request | **Partial** (mail.thread + some posts; not full resident/staff matrix) | No dedicated matrix test |
| High/Critical created alert | **Missing / Partial** | No |

---

## F. Integrations (§14)

| Integration | Status |
|---|---|
| Resident / unit fields on `res.partner` | **Done (code)** lightweight fields |
| Property master module deep sync | **Out of scope** / Partial fields only |
| Maintenance work-order link | **Missing** (ORM hook not present) |
| Vendor module | Waiting state `with_vendor` only; no vendor master link |
| Inventory / store | **Out of scope** |
| Mobile Helpdesk HTTP API | **Done (tested)** `/fms/helpdesk/api/v1/*` |

---

## G. Reports (§15)

| KPI area | Status | Tested? |
|---|---|---|
| Complaint volume / category / SLA compliance | **Done (tested)** | Yes |
| Avg response/resolution | **Done (tested)** | Yes |
| Escalations by reason | **Done (code)** | Partial |
| Team performance | **Done (tested)** | Yes |
| Reopened count | **Done (code)** | Via reports payload |
| Resident rating trends | **Partial** (Feedback screen; not full Reports charts) | No |
| CSV export | **Done (code)** | Analytics export rows tested |
| PDF / Excel export | **Missing** | — |

---

## H. Automated test run (this review)

Command:

```text
python odoo-bin -c odoo.conf -u fms_helpdesk --stop-after-init --test-enable --test-tags=fms_helpdesk --log-level=test
```

| Result | Count |
|---|---|
| Failed | **0** (first full run this review: 45 tests) |
| New tests added this review | Work Queue team tab; Settings reopen/feedback |

Latest automated run after follow-up fixes: **0 failed / 48 tests** (v18.0.1.10.0).

---

## I. Fixes applied in this review

1. Work Queue **Team** tab now filters `team_id.member_ids` (was incorrectly showing all open).
2. Dashboard quick actions: Complaints, SLA Breaches, Reports.
3. Ticket Details: Assign / Verify / Close / Reopen (+ reopen modal).
4. Settings UI: allow reopen, reopen days, feedback enabled, low-rating threshold.
5. Default ICP params for `app_name` and `require_verification`.
6. Docs: `INSTALL_AND_UPGRADE.md`, this checklist.
7. Follow-up from audits: waiting states no longer mark first response; Work Queue Assign column; Assign modal ticket picker; Assignment history table; Feedback CSV export; Categories header search; Ticket history action labels.

---

## J. Remaining gaps (priority)

1. Full resident notification matrix and comment/update UI on Ticket Details.
2. Reports: property filters, rating trends, PDF/Excel.
3. Bulk assignment; at-risk auto-escalation; seeded Critical/High/Medium/Low master data.
4. Maintenance work-order link when physical work is required.
5. Browser PPT visual QA for screens still only **Done (code)** (PPT text extract empty / image slides).
6. Editable ticket form (beyond create) from OWL; team-scoped agent ACLs; `sla_critical_warning_percent` still unused by engine.
