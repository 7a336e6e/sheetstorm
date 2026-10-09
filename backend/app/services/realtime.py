"""Realtime collaboration core (single owner of incident socket fan-out).

Rooms
-----
* ``incident_<id>``          base room: presence, ``incident``/``assignment``
                             entity events and resyncs for the ``incident``
                             scope. Joining requires incident access.
* ``incident_<id>:<scope>``  one room per entity scope. A socket is put in a
                             scope room **server-side at join time** only when
                             the user holds that scope's read permission, so a
                             Viewer without ``artifacts:read`` never receives
                             artifact payloads.
* ``user_<id>`` / ``org_<id>`` personal / organization rooms (connect time).

Every incident-entity change goes through :func:`emit_change` (after commit),
which emits one ``entity:changed`` envelope to the entity's scope room.
Bulk operations use :func:`emit_resync`. Cross-worker delivery and room
membership changes go through the Socket.IO Redis message queue
(``python-socketio`` ``PubSubManager`` propagates ``emit``, ``enter_room``,
``leave_room``, ``close_room`` and ``disconnect``).

Socket ids of authenticated sockets are kept in the Redis set
``ws:user_sids:<uid>`` so any worker (or the CLI) can evict or disconnect a
user's sockets. Presence lives in the Redis hash ``rt:presence:<incident>``.
Without Redis (unit tests / degraded mode) both fall back to in-process dicts
behind the same functions.

All emit helpers swallow and log errors: a realtime failure must never fail
the HTTP request that already committed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

BASE_SCOPE = 'incident'
OPS = ('created', 'updated', 'deleted')

SID_SET_TTL = 24 * 3600          # ws:user_sids:<uid>
SEQ_TTL = 7 * 24 * 3600          # rt:seq:<incident>:<scope>
PRESENCE_STALE_SECONDS = 75      # entries older than this are pruned on read
PRESENCE_KEY_TTL = 24 * 3600     # whole hash expires when an incident goes idle


@dataclass(frozen=True)
class EntitySpec:
    entity: str
    scope: str
    read_perm: str
    serializer: Optional[Callable] = None


ENTITY_SCOPES: dict[str, EntitySpec] = {}
SCOPE_PERMS: dict[str, str] = {}

# Audit resource_type -> entity name (for scope filtering of `activity:new`).
_RESOURCE_TYPE_ALIASES = {
    'compromised_host': 'host',
    'compromised_account': 'account',
    'network_indicator': 'network_ioc',
    'host_indicator': 'host_ioc',
    'host_based_indicator': 'host_ioc',
    'malware_tool': 'malware',
    'attack_graph_node': 'graph_node',
    'attack_graph_edge': 'graph_edge',
    'attack_graph_auto': 'graph_node',
    'incident_playbook': 'playbook',
    'incident_review': 'review',
    'incident_assignment': 'assignment',
    'chain_of_custody': 'custody_entry',
}


def register_entity(entity, scope, read_perm, serializer=None):
    """Register an incident entity type with its scope room and read permission.

    One scope maps to exactly one read permission; registering a scope with a
    different permission raises ValueError (it would make room membership
    ambiguous). Re-registering an entity replaces its spec (idempotent).
    """
    if not entity or not scope or not read_perm:
        raise ValueError('entity, scope and read_perm are required')
    existing = SCOPE_PERMS.get(scope)
    if existing is not None and existing != read_perm:
        raise ValueError(f'scope {scope!r} already bound to {existing!r}, not {read_perm!r}')
    SCOPE_PERMS[scope] = read_perm
    ENTITY_SCOPES[entity] = EntitySpec(entity, scope, read_perm, serializer)
    return ENTITY_SCOPES[entity]


def _serialize_account(obj):
    # Never reveal the password over the socket, whatever the caller holds.
    return obj.to_dict(reveal_password=False)


_ARTIFACT_PRIVATE_FIELDS = ('storage_path', 'extra_data')


def _serialize_artifact(obj):
    data = obj.to_dict()
    for key in _ARTIFACT_PRIVATE_FIELDS:
        data.pop(key, None)
    return data


def _register_defaults():
    for entity, scope, perm, ser in (
        ('incident', BASE_SCOPE, 'incidents:read', None),
        ('assignment', BASE_SCOPE, 'incidents:read', None),
        ('timeline_event', 'timeline', 'timeline:read', None),
        ('host', 'hosts', 'hosts:read', None),
        ('account', 'accounts', 'accounts:read', _serialize_account),
        ('network_ioc', 'network_iocs', 'network_iocs:read', None),
        ('host_ioc', 'host_iocs', 'host_iocs:read', None),
        ('malware', 'malware', 'malware:read', None),
        ('artifact', 'artifacts', 'artifacts:read', _serialize_artifact),
        ('task', 'tasks', 'tasks:read', None),
        ('task_comment', 'tasks', 'tasks:read', None),
        ('graph_node', 'attack_graph', 'attack_graph:read', None),
        ('graph_edge', 'attack_graph', 'attack_graph:read', None),
        ('case_note', 'notes', 'incidents:read', None),
        ('playbook', 'playbook', 'incidents:read', None),
        # Reserved for later work packages (they may re-register with a
        # serializer; scope + permission must stay as declared here).
        ('evidence_item', 'artifacts', 'artifacts:read', None),
        ('custody_entry', 'artifacts', 'artifacts:read', None),
        ('question', 'questions', 'incidents:read', None),
        ('decision', 'decisions', 'decisions:read', None),
        ('decision_privileged', 'decisions_privileged', 'decisions:read_privileged', None),
        ('response_action', 'response_actions', 'response_actions:read', None),
        ('review', 'review', 'incidents:read', None),
        ('improvement_action', 'improvements', 'improvements:read', None),
    ):
        register_entity(entity, scope, perm, ser)


_register_defaults()


# ---------------------------------------------------------------------------
# Rooms / scopes
# ---------------------------------------------------------------------------

def canonical_incident_id(value):
    """Return the canonical string form of an incident UUID, or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def base_room(incident_id):
    return f'incident_{incident_id}'


def scope_room(incident_id, scope):
    if scope == BASE_SCOPE:
        return base_room(incident_id)
    return f'incident_{incident_id}:{scope}'


def all_rooms(incident_id):
    """Base room plus every scope room of an incident."""
    rooms = [base_room(incident_id)]
    rooms.extend(scope_room(incident_id, s) for s in sorted(SCOPE_PERMS) if s != BASE_SCOPE)
    return rooms


def scope_for_entity(entity):
    spec = ENTITY_SCOPES.get(entity)
    return spec.scope if spec else None


def scope_for_resource_type(resource_type):
    """Map an audit ``resource_type`` (or entity name) to its scope, else None.

    Callers broadcasting incident activity must send events whose scope is
    None only where every incident member may see them (or drop them).
    """
    if not resource_type:
        return None
    entity = _RESOURCE_TYPE_ALIASES.get(resource_type, resource_type)
    return scope_for_entity(entity)


def known_resource_types() -> set:
    """Every name ``scope_for_resource_type`` can map: the registered entity
    names plus the audit ``resource_type`` aliases."""
    return set(ENTITY_SCOPES) | set(_RESOURCE_TYPE_ALIASES)


def scopes_for_user(user):
    """Scopes whose read permission the user holds (always includes the base
    scope when the user can read incidents)."""
    if not user:
        return []
    perms = set(user.permissions or [])
    return sorted(scope for scope, perm in SCOPE_PERMS.items() if perm in perms)


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------

_write_only_emitter = None
_emitter_override = None
_emitter_lock = threading.Lock()


def set_emitter(emitter):
    """Override the emitter (tests). Pass None to restore the default."""
    global _emitter_override
    _emitter_override = emitter


def _in_cli():
    try:
        import click
        return click.get_current_context(silent=True) is not None
    except Exception:  # pragma: no cover
        return False


def get_emitter():
    """The Socket.IO instance to emit with.

    Inside the server (and in tests) this is the app's ``socketio``. Under the
    Flask CLI (jobs) it is a lazily created **write-only**
    ``SocketIO(message_queue=REDIS_URL)`` that only publishes to Redis, so the
    CLI process never runs a pub/sub listener.
    """
    global _write_only_emitter
    if _emitter_override is not None:
        return _emitter_override
    from app import socketio
    if not _in_cli():
        return socketio
    try:
        from flask import current_app
        url = current_app.config.get('REDIS_URL')
        if current_app.testing or not url or not url.startswith(('redis://', 'rediss://')):
            return socketio
    except RuntimeError:
        return socketio
    with _emitter_lock:
        if _write_only_emitter is None:
            from flask_socketio import SocketIO
            _write_only_emitter = SocketIO(message_queue=url)
    return _write_only_emitter


def _server(emitter):
    return getattr(emitter, 'server', None)


# ---------------------------------------------------------------------------
# Redis helpers (with in-process fallback)
# ---------------------------------------------------------------------------

_local_lock = threading.Lock()
_local_sids: dict[str, set] = {}
_local_presence: dict[str, dict[str, str]] = {}


def _redis():
    try:
        import app as app_pkg
        return app_pkg.redis_client
    except Exception:  # pragma: no cover
        return None


def _sid_key(user_id):
    return f'ws:user_sids:{user_id}'


def register_sid(user_id, sid):
    r = _redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.sadd(_sid_key(user_id), sid)
            pipe.expire(_sid_key(user_id), SID_SET_TTL)
            pipe.execute()
            return
        except Exception:
            logger.warning('realtime: sid registry unavailable', exc_info=True)
    with _local_lock:
        _local_sids.setdefault(str(user_id), set()).add(sid)


def unregister_sid(user_id, sid):
    r = _redis()
    if r is not None:
        try:
            r.srem(_sid_key(user_id), sid)
        except Exception:
            logger.warning('realtime: sid registry unavailable', exc_info=True)
    with _local_lock:
        sids = _local_sids.get(str(user_id))
        if sids is not None:
            sids.discard(sid)
            if not sids:
                _local_sids.pop(str(user_id), None)


def user_sids(user_id):
    """All registered socket ids of a user (any worker)."""
    found = set()
    r = _redis()
    if r is not None:
        try:
            found.update(s.decode() if isinstance(s, bytes) else s
                         for s in r.smembers(_sid_key(user_id)))
        except Exception:
            logger.warning('realtime: sid registry unavailable', exc_info=True)
    with _local_lock:
        found.update(_local_sids.get(str(user_id), ()))
    return sorted(found)


def next_seq(incident_id, scope):
    """Per-(incident, scope) sequence number, or None without Redis."""
    r = _redis()
    if r is None:
        return None
    key = f'rt:seq:{incident_id}:{scope}'
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, SEQ_TTL)
        value, _ = pipe.execute()
        return int(value)
    except Exception:
        logger.warning('realtime: seq counter unavailable', exc_info=True)
        return None


def current_seqs(incident_id, scopes):
    """{scope: last seq (0 if none)} for the join ack; {} without Redis."""
    r = _redis()
    if r is None or not scopes:
        return {}
    try:
        values = r.mget([f'rt:seq:{incident_id}:{s}' for s in scopes])
        return {s: int(v) if v is not None else 0 for s, v in zip(scopes, values)}
    except Exception:
        logger.warning('realtime: seq counter unavailable', exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# Presence (Redis hash rt:presence:<incident>, field = opaque pid)
# ---------------------------------------------------------------------------

def _presence_key(incident_id):
    return f'rt:presence:{incident_id}'


def presence_set(incident_id, pid, entry):
    """Create/replace a presence entry. ``entry`` must not contain socket ids."""
    entry = dict(entry, ts=time.time())
    raw = json.dumps(entry, default=str)
    r = _redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.hset(_presence_key(incident_id), pid, raw)
            pipe.expire(_presence_key(incident_id), PRESENCE_KEY_TTL)
            pipe.execute()
            return
        except Exception:
            logger.warning('realtime: presence store unavailable', exc_info=True)
    with _local_lock:
        _local_presence.setdefault(str(incident_id), {})[pid] = raw


def presence_remove(incident_id, pids):
    pids = [p for p in (pids if isinstance(pids, (list, tuple, set)) else [pids]) if p]
    if not pids:
        return
    r = _redis()
    if r is not None:
        try:
            r.hdel(_presence_key(incident_id), *pids)
        except Exception:
            logger.warning('realtime: presence store unavailable', exc_info=True)
    with _local_lock:
        bucket = _local_presence.get(str(incident_id))
        if bucket:
            for p in pids:
                bucket.pop(p, None)


def _presence_raw(incident_id):
    r = _redis()
    if r is not None:
        try:
            return {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in r.hgetall(_presence_key(incident_id)).items()
            }
        except Exception:
            logger.warning('realtime: presence store unavailable', exc_info=True)
    with _local_lock:
        return dict(_local_presence.get(str(incident_id), {}))


def presence_list(incident_id, now=None):
    """Live presence entries; entries older than PRESENCE_STALE_SECONDS are
    pruned (so a crashed worker leaves no ghosts)."""
    now = time.time() if now is None else now
    users, stale = [], []
    for pid, raw in _presence_raw(incident_id).items():
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            stale.append(pid)
            continue
        if now - float(entry.get('ts') or 0) > PRESENCE_STALE_SECONDS:
            stale.append(pid)
            continue
        users.append({
            'pid': pid,
            'user_id': entry.get('user_id'),
            'name': entry.get('name'),
            'focus': entry.get('focus'),
            'mode': entry.get('mode') or 'viewing',
            'since': entry.get('since'),
        })
    if stale:
        presence_remove(incident_id, stale)
    users.sort(key=lambda u: (u.get('since') or '', u['pid']))
    return users


def presence_remove_user(incident_id, user_id):
    """Drop every presence entry of a user in an incident (eviction)."""
    pids = []
    for pid, raw in _presence_raw(incident_id).items():
        try:
            if json.loads(raw).get('user_id') == str(user_id):
                pids.append(pid)
        except (TypeError, ValueError):
            pids.append(pid)
    presence_remove(incident_id, pids)
    return pids


def presence_state_payload(incident_id):
    return {'incident_id': str(incident_id), 'users': presence_list(incident_id)}


def broadcast_presence(incident_id, emitter=None):
    try:
        emitter = emitter or get_emitter()
        emitter.emit('presence:state', presence_state_payload(incident_id),
                     to=base_room(incident_id))
    except Exception:
        logger.warning('realtime: presence broadcast failed', exc_info=True)


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------

def _actor():
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return None
        user = g.get('current_user')
        if user is not None:
            return {'id': str(user.id), 'name': user.name}
    except Exception:
        pass
    return None


def _id_of(value):
    if value is None:
        return None
    return str(value)


def build_envelope(incident_id, entity, op, obj=None, id=None, data=None, seq=None):
    """The ``entity:changed`` envelope (``data`` omitted for deletes)."""
    spec = ENTITY_SCOPES.get(entity)
    if spec is None:
        raise ValueError(f'unregistered realtime entity {entity!r}')
    if op not in OPS:
        raise ValueError(f'invalid op {op!r}')
    payload = None
    if op != 'deleted':
        if data is not None:
            payload = data
        elif obj is not None:
            payload = spec.serializer(obj) if spec.serializer else obj.to_dict()
    version = getattr(obj, 'version', None) if obj is not None else None
    if version is None and isinstance(payload, dict):
        version = payload.get('version')
    entity_id = id if id is not None else (getattr(obj, 'id', None) if obj is not None else None)
    if entity_id is None and isinstance(payload, dict):
        entity_id = payload.get('id')
    envelope = {
        'incident_id': str(incident_id),
        'entity': entity,
        'op': op,
        'id': _id_of(entity_id),
        'version': version,
        'scope': spec.scope,
        'seq': seq,
        'actor': _actor(),
        'at': datetime.now(timezone.utc).isoformat(),
    }
    if op != 'deleted':
        envelope['data'] = payload
    return envelope


def emit_change(incident_id, entity, op, obj=None, id=None, data=None):
    """Emit one ``entity:changed`` to the entity's scope room.

    Call only **after** ``db.session.commit()``. Never raises; returns the
    envelope (or None on failure) for tests and callers that log it.
    """
    try:
        iid = canonical_incident_id(incident_id)
        if iid is None:
            raise ValueError(f'invalid incident id {incident_id!r}')
        spec = ENTITY_SCOPES.get(entity)
        if spec is None:
            raise ValueError(f'unregistered realtime entity {entity!r}')
        # Build the payload first so a serializer failure doesn't burn a seq.
        envelope = build_envelope(iid, entity, op, obj=obj, id=id, data=data)
        envelope['seq'] = next_seq(iid, spec.scope)
        get_emitter().emit('entity:changed', envelope, to=scope_room(iid, spec.scope))
        return envelope
    except Exception:
        logger.exception('realtime: emit_change(%s, %s) failed', entity, op)
        return None


def emit_resync(incident_id, scopes=None, reason='bulk'):
    """Ask clients to refetch whole scopes (imports, bulk ops, auto actions).

    One ``incident:resync`` per scope room, so a scope's name only reaches
    users who can read it. ``scopes=None`` means every scope.
    """
    try:
        iid = canonical_incident_id(incident_id)
        if iid is None:
            raise ValueError(f'invalid incident id {incident_id!r}')
        if scopes is None:
            scopes = sorted(SCOPE_PERMS)
        elif isinstance(scopes, str):
            scopes = [scopes]
        emitter = get_emitter()
        sent = []
        for scope in dict.fromkeys(scopes):
            if scope not in SCOPE_PERMS:
                logger.warning('realtime: emit_resync unknown scope %r', scope)
                continue
            emitter.emit('incident:resync',
                         {'incident_id': iid, 'scopes': [scope], 'reason': str(reason)},
                         to=scope_room(iid, scope))
            sent.append(scope)
        return sent
    except Exception:
        logger.exception('realtime: emit_resync failed')
        return []


def emit_to_user(user_id, event, payload):
    """Emit to every socket of a user (``user_<id>`` room, all workers)."""
    try:
        get_emitter().emit(event, payload, to=f'user_{user_id}')
        return True
    except Exception:
        logger.exception('realtime: emit_to_user(%s) failed', event)
        return False


def evict_user_from_incident(user_id, incident_id, reason=None):
    """Remove a user's sockets from an incident's base + scope rooms (all
    workers, via the message queue), drop their presence and tell them via
    ``incident:access_revoked`` on ``user_<uid>``."""
    try:
        iid = canonical_incident_id(incident_id)
        if iid is None:
            raise ValueError(f'invalid incident id {incident_id!r}')
        emitter = get_emitter()
        server = _server(emitter)
        rooms = all_rooms(iid)
        for sid in user_sids(user_id):
            for room in rooms:
                try:
                    server.leave_room(sid, room, namespace='/')
                except Exception:
                    logger.debug('realtime: leave_room failed', exc_info=True)
        if presence_remove_user(iid, user_id):
            broadcast_presence(iid, emitter)
        payload = {'incident_id': iid}
        if reason:
            payload['reason'] = str(reason)
        emitter.emit('incident:access_revoked', payload, to=f'user_{user_id}')
        return True
    except Exception:
        logger.exception('realtime: evict_user_from_incident failed')
        return False


def disconnect_user_sockets(user_id):
    """Disconnect every socket of a user (all workers). The client reconnects
    and is re-authorized from scratch; a revoked token yields an anonymous
    connection. Use on deactivate, role/permission change, session revoke."""
    count = 0
    try:
        server = _server(get_emitter())
        for sid in user_sids(user_id):
            try:
                server.disconnect(sid, namespace='/')
                count += 1
            except Exception:
                logger.debug('realtime: disconnect failed', exc_info=True)
            unregister_sid(user_id, sid)
    except Exception:
        logger.exception('realtime: disconnect_user_sockets failed')
    return count


def notify_permissions_changed(user_ids):
    """Tell users their permissions changed, then disconnect their sockets so
    room membership is recomputed on reconnect."""
    if isinstance(user_ids, (str, uuid.UUID)):
        user_ids = [user_ids]
    for uid in dict.fromkeys(str(u) for u in (user_ids or []) if u):
        emit_to_user(uid, 'permissions_changed', {})
        disconnect_user_sockets(uid)


def close_incident_rooms(incident_id):
    """Close the base and all scope rooms of an incident (archive / purge).
    Callers emit ``incident:access_revoked`` to the base room first."""
    try:
        iid = canonical_incident_id(incident_id)
        server = _server(get_emitter())
        for room in all_rooms(iid):
            server.close_room(room, namespace='/')
        presence_remove(iid, list(_presence_raw(iid)))
        return True
    except Exception:
        logger.exception('realtime: close_incident_rooms failed')
        return False


def _reset_local_state():
    """Test helper: clear in-process fallbacks."""
    with _local_lock:
        _local_sids.clear()
        _local_presence.clear()


__all__ = [
    'BASE_SCOPE', 'ENTITY_SCOPES', 'SCOPE_PERMS', 'register_entity', 'scope_for_entity',
    'scope_for_resource_type', 'known_resource_types', 'scopes_for_user', 'base_room', 'scope_room', 'all_rooms',
    'canonical_incident_id', 'get_emitter', 'set_emitter', 'build_envelope', 'emit_change',
    'emit_resync', 'emit_to_user', 'evict_user_from_incident', 'disconnect_user_sockets',
    'notify_permissions_changed', 'close_incident_rooms', 'register_sid', 'unregister_sid',
    'user_sids', 'next_seq', 'current_seqs', 'presence_set', 'presence_remove',
    'presence_list', 'presence_remove_user', 'broadcast_presence',
]
