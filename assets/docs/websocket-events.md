# WebSocket Events

Socket.IO on the backend origin (`/socket.io/`). Authentication happens once,
at connect time, from the first valid **interactive access JWT** found in (in
order) the Socket.IO `auth` payload `{ token }`, the `?token=` query string,
the `Authorization: Bearer` header, or the httpOnly `access_token_cookie`.
Refresh tokens, MFA pre-auth tokens, API-key tokens and tokens of inactive /
revoked users give an **anonymous** connection, which can only `ping`.

Identity is never read from event payloads. Server code lives in
`backend/app/api/websocket/__init__.py`; emit helpers in
`backend/app/services/realtime.py`.

---

## Rooms

| Room | Members | Carries |
|---|---|---|
| `user_<id>` | every socket of that user (connect) | `notification`, `permissions_changed`, `session:revoked`, `incident:access_revoked` |
| `org_<id>` | every socket of the org (connect) | org-wide `activity:new` |
| `incident_<id>` | sockets that passed the incident access check on `incident:join` | `presence:state`, `entity:changed` for `incident`/`assignment`, `incident:resync` for scope `incident`, `activity:new` |
| `incident_<id>:<scope>` | joined sockets whose user holds the scope's read permission | `entity:changed`, `incident:resync`, `graph:node_drag` (scope `attack_graph`) |

Clients never choose rooms; the server derives the scope rooms at join time.
A permission change takes effect on reconnect (`notify_permissions_changed`
disconnects the user's sockets).

### Scopes and entities

| Scope | Read permission | Entities |
|---|---|---|
| `incident` (base room) | `incidents:read` | `incident`, `assignment` |
| `timeline` | `timeline:read` | `timeline_event` |
| `hosts` | `hosts:read` | `host` |
| `accounts` | `accounts:read` | `account` (password always masked) |
| `network_iocs` | `network_iocs:read` | `network_ioc` |
| `host_iocs` | `host_iocs:read` | `host_ioc` |
| `malware` | `malware:read` | `malware` |
| `artifacts` | `artifacts:read` | `artifact` (no `storage_path`/`extra_data`), `evidence_item`, `custody_entry` |
| `tasks` | `tasks:read` | `task`, `task_comment` |
| `attack_graph` | `attack_graph:read` | `graph_node`, `graph_edge` |
| `notes` | `incidents:read` | `case_note` |
| `playbook` | `incidents:read` | `playbook` |
| `questions` | `incidents:read` | `question` |
| `decisions` | `decisions:read` | `decision` |
| `decisions_privileged` | `decisions:read_privileged` | `decision_privileged` |
| `response_actions` | `response_actions:read` | `response_action` |
| `review` | `incidents:read` | `review` |
| `improvements` | `improvements:read` | `improvement_action` |

New entities register with `realtime.register_entity(entity, scope, read_perm, serializer=None)`.

---

## Client → Server

Every event is rate limited per socket (token bucket) and validated; invalid
input is dropped with `rt:error`.

| Event | Payload | Notes |
|---|---|---|
| `incident:join` | `{ incident_id }` | Requires incident access. Max 5 incidents per socket (the 6th join leaves the oldest). 10/min. Ack + `incident:joined`. |
| `incident:leave` | `{ incident_id }` | Ignored unless the socket joined that incident. |
| `presence:update` | `{ incident_id, focus: {entity, id} \| null, mode: 'viewing' \| 'editing' }` | Send debounced (300 ms) and as a 25 s heartbeat. `focus.entity` must be in a scope the user can read. 4/s, burst 8. |
| `graph:node_drag` | `{ incident_id, node_id, x, y }` | Requires `attack_graph:update`; node must belong to the incident; finite `|x|,|y| < 1e6`. 15/s. |
| `ping` | — | Allowed for anonymous sockets. |

Other events: 20/s. More than 50 rate-limit violations in 60 s logs the
security event `ws_rate_limited` and disconnects the socket. Denied joins log
`ws_join_denied` (at most once per socket per minute). Frames are capped at
64 KB (`max_http_buffer_size`).

## Server → Client

| Event | Room | Payload |
|---|---|---|
| `connected` | self | `{ user_id, name }` or `{ anonymous: true }` |
| `incident:joined` | self (also the join ack) | `{ incident_id, scopes: [..], seq: {scope: int}, presence: [...] }` |
| `entity:changed` | scope room | envelope below |
| `incident:resync` | scope room (one per scope) | `{ incident_id, scopes: [scope], reason }` |
| `incident:access_revoked` | `user_<id>` | `{ incident_id, reason? }` |
| `presence:state` | `incident_<id>` | `{ incident_id, users: [{ pid, user_id, name, focus, mode, since }] }` — never socket ids; updates throttled to 1/s per incident, joins/leaves immediate |
| `graph:node_drag` | `incident_<id>:attack_graph` (not echoed) | `{ incident_id, node_id, x, y, user_id }` |
| `rt:error` | self | `{ code: 'denied' \| 'rate_limited' \| 'invalid', event }` |
| `permissions_changed` | `user_<id>` | `{}` (sockets are then disconnected) |
| `session:revoked` | `user_<id>` | `{ reason }` |
| `notification` | `user_<id>` | `Notification` |
| `activity:new` | incident / org / admin user rooms | audit activity item |
| `pong` | self | — |

### `entity:changed` envelope

```json
{"incident_id": "uuid", "entity": "task", "op": "created|updated|deleted",
 "id": "uuid", "version": 7, "scope": "tasks", "seq": 1234,
 "actor": {"id": "uuid", "name": "Dana"}, "at": "ISO-8601",
 "data": {"...": "same dict the list endpoint returns"}}
```

`data` is omitted for `deleted`. `seq` is a per-(incident, scope) counter
(Redis `rt:seq:<incident>:<scope>`, 7-day TTL); a gap means missed events, so
resync that scope. `seq` is `null` when Redis is unavailable. Apply `updated`
only when `version` is newer than the local copy.

### Legacy events (until W1-RT-EMIT)

Endpoints still emit the legacy `*_added` / `*_updated` / `*_deleted` events to
`incident_<id>`; they have no frontend consumer and are removed when the
endpoints switch to `realtime.emit_change`. The old client events
`join_incident`, `leave_incident`, `cursor_move`, `typing_*` and
`graph_node_moved` (and `user_joined`, `user_left`, `users_in_room`,
`cursor_moved`, `user_typing`, `graph_node_position`) were removed.

---

## Server-side API (`app/services/realtime.py`)

- `emit_change(incident_id, entity, op, obj=None, id=None, data=None)` — after commit only.
- `emit_resync(incident_id, scopes=None, reason='bulk')`
- `emit_to_user(user_id, event, payload)`
- `evict_user_from_incident(user_id, incident_id, reason=None)`
- `disconnect_user_sockets(user_id)`, `notify_permissions_changed(user_ids)`
- `close_incident_rooms(incident_id)` (archive / purge, after emitting `incident:access_revoked`)
- `scope_for_resource_type(resource_type)`, `scopes_for_user(user)`, `register_entity(...)`
- `get_emitter()` — the app `socketio` in the server; a write-only Redis emitter under the Flask CLI.

Socket ids are tracked in Redis `ws:user_sids:<uid>`; presence in
`rt:presence:<incident>` (entries older than 75 s are pruned on read).
Cross-worker delivery uses the Socket.IO Redis message queue (`REDIS_URL`).

## Optimistic concurrency

Versioned rows expose `version`. Send `If-Match: "<version>"` (or the body key
the endpoint documents, default `expected_version`) on PUT/PATCH/DELETE; a
stale version returns `409 {error: 'conflict', current, current_version}`.
Responses may carry `ETag: "<version>"`.
