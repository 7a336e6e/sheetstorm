# API Reference

All endpoints are prefixed with `/api/v1`. Authentication via `Authorization: Bearer <token>` header.

---

## Authentication

| Method | Endpoint           | Description          | Rate Limit |
|--------|--------------------|----------------------|------------|
| POST   | `/auth/register`   | Register new user    | 3/hour     |
| POST   | `/auth/login`      | Login                | 5/minute   |
| POST   | `/auth/logout`     | Logout (revoke JWT)  | —          |
| POST   | `/auth/refresh`    | Refresh access token | —          |
| GET    | `/auth/me`         | Current user info    | —          |
| PUT    | `/auth/password`   | Change password      | —          |

## Incidents

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents`                              | List incidents (paginated)     |
| POST   | `/incidents`                              | Create incident                |
| GET    | `/incidents/{id}`                         | Get incident details           |
| PUT    | `/incidents/{id}`                         | Update incident                |
| DELETE | `/incidents/{id}`                         | Delete incident                |
| PATCH  | `/incidents/{id}/status`                  | Update status/phase            |
| POST   | `/incidents/{id}/import/parse`            | Parse Excel file               |
| POST   | `/incidents/{id}/import/submit`           | Submit mapped import data      |

## Timeline Events

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/timeline`                | List timeline events           |
| POST   | `/incidents/{id}/timeline`                | Create event                   |
| PUT    | `/incidents/{id}/timeline/{eid}`          | Update event                   |
| DELETE | `/incidents/{id}/timeline/{eid}`          | Delete event                   |
| POST   | `/incidents/{id}/timeline/{eid}/mark-ioc` | Flag event as IOC              |
| GET    | `/mitre/tactics`                          | List MITRE tactics             |
| GET    | `/mitre/techniques/{tactic}`              | List techniques for tactic     |

## Compromised Assets

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/hosts`                   | List compromised hosts         |
| POST   | `/incidents/{id}/hosts`                   | Add compromised host           |
| PUT    | `/incidents/{id}/hosts/{hid}`             | Update host                    |
| DELETE | `/incidents/{id}/hosts/{hid}`             | Delete host                    |
| GET    | `/incidents/{id}/accounts`                | List compromised accounts      |
| POST   | `/incidents/{id}/accounts`                | Add account (password encrypted)|
| PUT    | `/incidents/{id}/accounts/{aid}`          | Update account                 |
| DELETE | `/incidents/{id}/accounts/{aid}`          | Delete account                 |
| GET    | `/incidents/{id}/accounts/{aid}/reveal`   | Reveal decrypted password      |

## IOCs

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/network-iocs`            | List network indicators        |
| POST   | `/incidents/{id}/network-iocs`            | Add network IOC                |
| PUT    | `/incidents/{id}/network-iocs/{nid}`      | Update network IOC             |
| DELETE | `/incidents/{id}/network-iocs/{nid}`      | Delete network IOC             |
| GET    | `/incidents/{id}/host-iocs`               | List host-based indicators     |
| POST   | `/incidents/{id}/host-iocs`               | Add host IOC                   |
| PUT    | `/incidents/{id}/host-iocs/{hid}`         | Update host IOC                |
| DELETE | `/incidents/{id}/host-iocs/{hid}`         | Delete host IOC                |
| GET    | `/incidents/{id}/malware`                 | List malware/tools             |
| POST   | `/incidents/{id}/malware`                 | Add malware entry              |
| PUT    | `/incidents/{id}/malware/{mid}`           | Update malware entry           |
| DELETE | `/incidents/{id}/malware/{mid}`           | Delete malware entry           |

## Attack Graph

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/attack-graph`            | Full graph with correlations   |
| POST   | `/incidents/{id}/attack-graph/auto-generate` | Auto-generate from data     |
| GET    | `/incidents/{id}/attack-graph/nodes`      | List nodes                     |
| POST   | `/incidents/{id}/attack-graph/nodes`      | Create node                    |
| PUT    | `/incidents/{id}/attack-graph/nodes/{nid}`| Update node                    |
| DELETE | `/incidents/{id}/attack-graph/nodes/{nid}`| Delete node                    |
| GET    | `/incidents/{id}/attack-graph/edges`      | List edges                     |
| POST   | `/incidents/{id}/attack-graph/edges`      | Create edge                    |
| PUT    | `/incidents/{id}/attack-graph/edges/{eid}`| Update edge                    |
| DELETE | `/incidents/{id}/attack-graph/edges/{eid}`| Delete edge                    |
| GET    | `/attack-graph/node-types`                | Available node types           |
| GET    | `/attack-graph/edge-types`                | Available edge types           |

## Artifacts & Evidence

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/artifacts`               | List artifacts                 |
| POST   | `/incidents/{id}/artifacts`               | Upload artifact (multipart)    |
| GET    | `/incidents/{id}/artifacts/{aid}/download` | Download artifact             |
| POST   | `/incidents/{id}/artifacts/{aid}/verify`  | Verify integrity               |
| GET    | `/incidents/{id}/artifacts/{aid}/custody` | Chain of custody log           |

## Tasks

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/tasks`                   | List tasks                     |
| POST   | `/incidents/{id}/tasks`                   | Create task                    |
| PUT    | `/incidents/{id}/tasks/{tid}`             | Update task                    |
| DELETE | `/incidents/{id}/tasks/{tid}`             | Delete task                    |
| POST   | `/incidents/{id}/tasks/{tid}/comments`    | Add comment                    |
| GET    | `/incidents/{id}/tasks/{tid}/comments`    | List comments                  |

## Reports

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| POST   | `/incidents/{id}/reports/generate-pdf`    | Generate PDF report            |
| POST   | `/incidents/{id}/reports/ai-generate`     | Generate AI summary            |
| GET    | `/incidents/{id}/reports`                 | List reports                   |

## Admin & System

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/users`                                  | List users                     |
| POST   | `/users`                                  | Create user                    |
| GET    | `/users/{id}`                             | Get user details               |
| PUT    | `/users/{id}`                             | Update user                    |
| DELETE | `/users/{id}`                             | Deactivate user                |
| GET    | `/users/{id}/roles`                       | Get user roles                 |
| POST   | `/users/{id}/roles`                       | Assign role                    |
| DELETE | `/users/{id}/roles/{rid}`                 | Remove role                    |
| GET    | `/roles`                                  | List roles                     |
| GET    | `/teams`                                  | List teams                     |
| POST   | `/teams`                                  | Create team                    |
| GET    | `/notifications`                          | List notifications             |
| PUT    | `/notifications/{id}/read`                | Mark as read                   |
| POST   | `/notifications/mark-all-read`            | Mark all as read               |
| GET    | `/audit-logs`                             | List audit logs (paginated)    |
| GET    | `/audit-logs/stats`                       | Audit statistics               |
| GET    | `/integrations`                           | List integrations              |
| POST   | `/integrations`                           | Create integration             |
| GET    | `/health`                                 | Health check                   |
