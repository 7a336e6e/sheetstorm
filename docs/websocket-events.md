# WebSocket Events

Connect via Socket.IO at `NEXT_PUBLIC_WS_URL` with `?token=<jwt>` query param.

---

## Client → Server

| Event              | Payload                                           | Description                |
|--------------------|---------------------------------------------------|----------------------------|
| `join_incident`    | `{ incident_id, user_id, user_name }`             | Join incident room         |
| `leave_incident`   | `{ incident_id }`                                 | Leave incident room        |
| `cursor_move`      | `{ incident_id, user_id, user_name, position }`   | Broadcast cursor position  |
| `typing_start`     | `{ incident_id, user_id, user_name, field }`       | Typing indicator on        |
| `typing_stop`      | `{ incident_id, user_id, field }`                  | Typing indicator off       |
| `graph_node_moved` | `{ incident_id, node_id, position, user_id }`      | Sync node position         |
| `ping`             | —                                                 | Keep-alive                 |

## Server → Client

| Event                  | Payload                                       | Description                |
|------------------------|-----------------------------------------------|----------------------------|
| `connected`            | `{ user_id, name }` or `{ anonymous: true }`  | Connection acknowledged    |
| `user_joined`          | `{ sid, user_id, name }`                       | User entered room          |
| `user_left`            | `{ sid }`                                      | User left room             |
| `users_in_room`        | `{ users: [...] }`                             | Current room roster        |
| `cursor_moved`         | `{ user_id, user_name, position }`             | Other user's cursor        |
| `user_typing`          | `{ user_id, user_name, field, typing }`        | Other user typing          |
| `graph_node_position`  | `{ node_id, position, user_id }`               | Other user moved node      |
| `notification`         | `Notification`                                 | Real-time notification     |
| `graph_node_added`     | `AttackGraphNode`                              | Node created via API       |
| `graph_node_updated`   | `AttackGraphNode`                              | Node updated via API       |
| `graph_node_deleted`   | `{ id }`                                       | Node deleted via API       |
| `graph_edge_added`     | `AttackGraphEdge`                              | Edge created via API       |
| `graph_edge_updated`   | `AttackGraphEdge`                              | Edge updated via API       |
| `graph_edge_deleted`   | `{ id }`                                       | Edge deleted via API       |
| `pong`                 | —                                              | Keep-alive response        |
