# FMS Helpdesk API Contracts

## Which integrations need HTTP APIs?

| Integration | Needs HTTP API? | Reason |
|---|---|---|
| In-Odoo OWL Helpdesk UI | **No** | Already uses session ORM RPC (`orm.call` → `fms.helpdesk.ui`). |
| Mobile Helpdesk (resident / staff) | **Yes** | External client cannot call the ORM; Functional Scope §14 lists Mobile Helpdesk. |
| Resident / Property masters | **No (HTTP)** | Read via existing `res.partner` fields on the ticket; owned by master modules. |
| Maintenance / Vendor / Inventory | **No (HTTP)** | In-FMS modules should call `fms.helpdesk.ticket` ORM methods. HTTP only if a non-Odoo system appears later. |

Business rules stay on ticket / resolution / escalation / feedback models. Controllers only authenticate, validate input, and serialize.

## Authentication

- Endpoints use `auth=public` at the HTTP layer, then require an **authenticated Odoo session** (`request.session.uid`).
- Mobile / external clients must log in first (for example `POST /web/session/authenticate`) and send the session cookie.
- The user must belong to a Helpdesk group (Resident, Agent, Team Lead, Manager, Admin, or Viewer).
- Optional header: `X-Request-Id` (echoed in the JSON body when present).

## Response envelope

Success:

```json
{
  "success": true,
  "data": { },
  "error": null,
  "request_id": "optional"
}
```

Failure:

```json
{
  "success": false,
  "data": null,
  "error": { "code": "VALIDATION_ERROR|UNAUTHORIZED|NOT_FOUND|SERVER_ERROR", "message": "..." },
  "request_id": "optional"
}
```

HTTP status mirrors the error: `400`, `401`, `404`, `500`.

## Endpoints

Base path: `/fms/helpdesk/api/v1`

### `GET /masters`

Returns categories (with subcategories), priorities, teams, escalation levels, and the current user profile.

### `GET /tickets`

Query params:

| Param | Type | Notes |
|---|---|---|
| `search` | string | Ticket id / title / description |
| `state` | string | Ticket state code |
| `category_id` | int | |
| `priority_id` | int | |
| `mine` | bool | Resident: own tickets. Staff: assigned to me |
| `include_draft` | bool | Default false |
| `limit` | int | Default 50, max 200 |
| `offset` | int | |

### `POST /tickets`

Body:

```json
{
  "title": "Water Leakage",
  "description": "Kitchen sink drip",
  "category_id": 1,
  "subcategory_id": 2,
  "priority_id": 3,
  "resident_id": 10,
  "contact_name": "optional if no resident_id (staff)",
  "building_name": "Tower A",
  "unit_name": "A-101",
  "location_type": "apartment_inside",
  "submit": true
}
```

Creates through `fms.helpdesk.ticket.create` / submit. Channel is set to `mobile`. Residents are forced to their own partner.

### `GET /tickets/<id>`

Full ticket detail, history, attachments and feedback. Missing id → `NOT_FOUND`. Hidden by record rules → `UNAUTHORIZED`.

### `POST /tickets/<id>/updates`

```json
{ "note": "Additional information from resident" }
```

Posts a chatter comment (audit + first-response SLA behaviour unchanged).

### `POST /tickets/<id>/assign`

```json
{ "team_id": 1, "user_id": 2, "reason": "Workload balancing" }
```

Calls `ticket.action_assign`.

### `POST /tickets/<id>/escalate`

```json
{ "level_id": 1, "reason": "sla_breached", "comment": "..." }
```

Calls `ticket.action_escalate`.

### `POST /tickets/<id>/resolve`

```json
{ "description": "Pipe joint replaced", "work_performed": "Pressure tested" }
```

Calls `ticket.action_add_resolution`.

### `POST /tickets/<id>/verify`

```json
{ "remarks": "Confirmed on site" }
```

Calls `resolution.action_verify`.

### `POST /tickets/<id>/close`

```json
{ "reason": "resolved", "comment": "Closed" }
```

Calls `ticket.action_close`.

### `POST /tickets/<id>/reopen`

```json
{ "reason": "Leak returned" }
```

Calls `ticket.action_reopen`.

### `POST /tickets/<id>/feedback`

```json
{ "rating": "4", "comment": "Good work" }
```

Updates a pending feedback row or creates a submitted one via `fms.helpdesk.feedback`.

## In-Odoo frontend

The OWL Helpdesk app continues to use `orm.call("fms.helpdesk.ui", ...)` inside the authenticated backend session. That path already enforces ACLs and reuses the same ORM methods. It is intentionally **not** rewritten onto these HTTP routes.
