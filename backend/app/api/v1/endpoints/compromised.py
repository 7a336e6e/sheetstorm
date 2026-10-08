"""Compromised assets endpoints"""
from datetime import datetime
from flask import jsonify, request, g
from flask_jwt_extended import jwt_required
from dateutil.parser import parse as parse_date
from app.api.v1 import api_bp
from app import db, socketio
from app.models import CompromisedHost, CompromisedAccount, TimelineEvent
from app.middleware.rbac import require_permission, require_incident_access, get_current_user
from app.middleware.audit import audit_log, log_security_event
from app.services.encryption_service import encryption_service
from app.utils.pagination import list_response
from app.utils.validation import parse_datetime, check_choice, json_body


# =============================================================================
# Compromised Hosts
# =============================================================================

HOST_SORTABLE = {
    'first_seen': CompromisedHost.first_seen,
    'last_seen': CompromisedHost.last_seen,
    'hostname': CompromisedHost.hostname,
    'containment_status': CompromisedHost.containment_status,
    'created_at': CompromisedHost.created_at,
}


@api_bp.route('/incidents/<uuid:incident_id>/hosts', methods=['GET'])
@jwt_required()
@require_incident_access('hosts:read')
def list_compromised_hosts(incident_id):
    """List compromised hosts (utils/pagination.py contract; q/search over
    hostname, IP, system_type, notes; filter containment_status)."""
    incident = g.incident
    query = CompromisedHost.query.filter_by(incident_id=incident.id)
    return jsonify(list_response(
        query, sortable=HOST_SORTABLE, default_sort='-first_seen', id_col=CompromisedHost.id,
        filters={'containment_status': (CompromisedHost.containment_status, 'eq')},
        search_columns=(CompromisedHost.hostname, CompromisedHost.ip_address,
                        CompromisedHost.system_type, CompromisedHost.notes),
        serialize=lambda h: h.to_dict(),
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/hosts', methods=['POST'])
@jwt_required()
@require_incident_access('hosts:create')
@audit_log('data_modification', 'create', 'compromised_host')
def create_compromised_host(incident_id):
    """Add a compromised host."""
    user = get_current_user()
    incident = g.incident
    data = json_body()

    hostname = data.get('hostname') if isinstance(data.get('hostname'), str) else ''
    hostname = hostname.strip()
    if not hostname:
        return jsonify({'error': 'bad_request', 'message': 'hostname is required'}), 400

    triage_status = check_choice(data.get('triage_status') or 'under_analysis',
                                 CompromisedHost.TRIAGE_STATUSES, 'triage_status')
    first_seen = parse_datetime(data.get('first_seen'), 'first_seen')
    last_seen = parse_datetime(data.get('last_seen'), 'last_seen')

    status = data.get('containment_status') or 'active'
    if status not in CompromisedHost.CONTAINMENT_STATUSES:
        return jsonify({
            'error': 'bad_request',
            'message': f'Invalid containment_status: {status}. '
                       f'Valid values: {CompromisedHost.CONTAINMENT_STATUSES}'
        }), 400

    host = CompromisedHost(
        incident_id=incident.id,
        hostname=hostname,
        ip_address=data.get('ip_address'),
        mac_address=data.get('mac_address'),
        system_type=data.get('system_type'),
        os_version=data.get('os_version'),
        evidence=data.get('evidence'),
        first_seen=first_seen,
        last_seen=last_seen,
        containment_status=status,
        triage_status=triage_status,
        acquisition_status=data.get('acquisition_status') or {},
        notes=data.get('notes'),
        extra_data=data.get('extra_data') or {},
        created_by=user.id
    )

    db.session.add(host)
    db.session.commit()

    socketio.emit('host_added', host.to_dict(), room=f'incident_{incident_id}')

    return jsonify(host.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/hosts/<uuid:host_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('hosts:update')
@audit_log('data_modification', 'update', 'compromised_host')
def update_compromised_host(incident_id, host_id):
    """Update a compromised host."""
    incident = g.incident
    data = json_body()

    host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
    if not host:
        return jsonify({'error': 'not_found', 'message': 'Host not found'}), 404

    if 'hostname' in data and (not isinstance(data['hostname'], str) or not data['hostname'].strip()):
        return jsonify({'error': 'bad_request', 'message': 'hostname must be a non-empty string'}), 400
    if 'triage_status' in data:
        # Explicit null resets to the default (column is NOT NULL).
        data['triage_status'] = check_choice(data['triage_status'] or 'under_analysis',
                                             CompromisedHost.TRIAGE_STATUSES, 'triage_status')
    if 'first_seen' in data:
        data['first_seen'] = parse_datetime(data['first_seen'], 'first_seen')
    if 'last_seen' in data:
        data['last_seen'] = parse_datetime(data['last_seen'], 'last_seen')

    # Validate containment_status before applying
    if 'containment_status' in data and data['containment_status'] not in CompromisedHost.CONTAINMENT_STATUSES:
        return jsonify({
            'error': 'bad_request',
            'message': f"Invalid containment_status: {data['containment_status']}. "
                       f'Valid values: {CompromisedHost.CONTAINMENT_STATUSES}'
        }), 400

    # Update fields
    for field in ['hostname', 'ip_address', 'mac_address', 'system_type', 'os_version',
                  'evidence', 'containment_status', 'triage_status', 'acquisition_status',
                  'notes', 'extra_data']:
        if field in data:
            setattr(host, field, data[field])

    if 'first_seen' in data:
        host.first_seen = data['first_seen']
    if 'last_seen' in data:
        host.last_seen = data['last_seen']

    db.session.commit()

    return jsonify(host.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/hosts/<uuid:host_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('hosts:delete')
@audit_log('data_modification', 'delete', 'compromised_host')
def delete_compromised_host(incident_id, host_id):
    """Delete a compromised host."""
    incident = g.incident

    host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
    if not host:
        return jsonify({'error': 'not_found', 'message': 'Host not found'}), 404

    db.session.delete(host)
    db.session.commit()

    return jsonify({'message': 'Host deleted'}), 200


# =============================================================================
# Compromised Accounts
# =============================================================================

ACCOUNT_SORTABLE = {
    'datetime_seen': CompromisedAccount.datetime_seen,
    'account_name': CompromisedAccount.account_name,
    'domain': CompromisedAccount.domain,
    'status': CompromisedAccount.status,
    'is_privileged': CompromisedAccount.is_privileged,
    'created_at': CompromisedAccount.created_at,
}
ACCOUNT_FILTERS = {
    'account_type': (CompromisedAccount.account_type, 'eq'),
    'status': (CompromisedAccount.status, 'eq'),
    'host_id': (CompromisedAccount.host_id, 'uuid'),
}


@api_bp.route('/incidents/<uuid:incident_id>/accounts', methods=['GET'])
@jwt_required()
@require_incident_access('accounts:read')
def list_compromised_accounts(incident_id):
    """List compromised accounts (utils/pagination.py contract; q/search over
    account name, domain, host, notes — never the password; filters
    account_type, status, host_id; `reveal=true` as before)."""
    user = get_current_user()
    incident = g.incident
    reveal = request.args.get('reveal', 'false').lower() == 'true'
    query = CompromisedAccount.query.filter_by(incident_id=incident.id)

    # Check permission to reveal passwords
    can_reveal = reveal and user.has_permission('compromised_accounts:reveal')

    def serialize(account):
        decrypted_password = None
        if can_reveal and account.password_encrypted:
            try:
                decrypted_password = encryption_service.decrypt(account.password_encrypted)
                # Log password reveal
                log_security_event(
                    action='password_reveal',
                    resource_type='compromised_account',
                    resource_id=account.id,
                    incident_id=incident.id,
                    details={'account_name': account.account_name}
                )
            except Exception:
                pass
        return account.to_dict(reveal_password=can_reveal, decrypted_password=decrypted_password)

    return jsonify(list_response(
        query, sortable=ACCOUNT_SORTABLE, default_sort='-datetime_seen', id_col=CompromisedAccount.id,
        filters=ACCOUNT_FILTERS,
        search_columns=(CompromisedAccount.account_name, CompromisedAccount.domain,
                        CompromisedAccount.host_system, CompromisedAccount.notes),
        serialize=serialize,
    )), 200


@api_bp.route('/incidents/<uuid:incident_id>/accounts/<uuid:account_id>', methods=['GET'])
@jwt_required()
@require_incident_access('accounts:read')
def get_compromised_account(incident_id, account_id):
    """Get one compromised account (same shape as a list item).

    `?reveal=true` decrypts ONLY this account's password; it requires the
    compromised_accounts:reveal permission (403 otherwise) and writes exactly
    one password_reveal security event.
    """
    user = get_current_user()
    incident = g.incident
    reveal = request.args.get('reveal', 'false').lower() == 'true'

    account = CompromisedAccount.query.filter_by(id=account_id, incident_id=incident.id).first()
    if not account:
        return jsonify({'error': 'not_found', 'message': 'Account not found'}), 404

    if reveal and not user.has_permission('compromised_accounts:reveal'):
        return jsonify({
            'error': 'forbidden',
            'message': 'Permission denied. Required: compromised_accounts:reveal'
        }), 403

    decrypted_password = None
    if reveal and account.password_encrypted:
        decrypted_password = encryption_service.decrypt(account.password_encrypted)
        log_security_event(
            action='password_reveal',
            resource_type='compromised_account',
            resource_id=account.id,
            incident_id=incident.id,
            details={'account_name': account.account_name}
        )

    return jsonify(account.to_dict(reveal_password=reveal, decrypted_password=decrypted_password)), 200


@api_bp.route('/incidents/<uuid:incident_id>/accounts', methods=['POST'])
@jwt_required()
@require_incident_access('accounts:create')
@audit_log('data_modification', 'create', 'compromised_account')
def create_compromised_account(incident_id):
    """Add a compromised account."""
    user = get_current_user()
    incident = g.incident
    data = request.get_json()

    if not data:
        return jsonify({'error': 'bad_request', 'message': 'No data provided'}), 400

    account_name = data.get('account_name', '').strip()
    if not account_name:
        return jsonify({'error': 'bad_request', 'message': 'account_name is required'}), 400

    datetime_seen = data.get('datetime_seen')
    if not datetime_seen:
        return jsonify({'error': 'bad_request', 'message': 'datetime_seen is required'}), 400

    account_type = data.get('account_type', 'local')
    if account_type not in CompromisedAccount.ACCOUNT_TYPES:
        return jsonify({'error': 'bad_request', 'message': 'Invalid account_type'}), 400

    # Encrypt password if provided
    password_encrypted = None
    if data.get('password'):
        try:
            password_encrypted = encryption_service.encrypt(data['password'])
        except Exception as e:
            return jsonify({'error': 'server_error', 'message': 'Failed to encrypt password'}), 500

    # Validate host_id if provided
    host_id = data.get('host_id')
    host_system = data.get('host_system')
    if host_id:
        host = CompromisedHost.query.filter_by(id=host_id, incident_id=incident.id).first()
        if not host:
            return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
        host_system = host.hostname  # Auto-fill host_system from host

    # Validate timeline_event_id if provided
    timeline_event_id = data.get('timeline_event_id')
    if timeline_event_id:
        event = TimelineEvent.query.filter_by(id=timeline_event_id, incident_id=incident.id).first()
        if not event:
            return jsonify({'error': 'bad_request', 'message': 'Invalid timeline_event_id'}), 400

    account = CompromisedAccount(
        incident_id=incident.id,
        host_id=host_id,
        timeline_event_id=timeline_event_id,
        datetime_seen=parse_datetime(datetime_seen, 'datetime_seen', required=True),
        account_name=account_name,
        password_encrypted=password_encrypted,
        host_system=host_system,
        sid=data.get('sid'),
        account_type=account_type,
        domain=data.get('domain'),
        is_privileged=data.get('is_privileged', False),
        status=data.get('status', 'active'),
        notes=data.get('notes'),
        extra_data=data.get('extra_data', {}),
        created_by=user.id
    )

    db.session.add(account)
    db.session.commit()

    return jsonify(account.to_dict()), 201


@api_bp.route('/incidents/<uuid:incident_id>/accounts/<uuid:account_id>', methods=['PUT'])
@jwt_required()
@require_incident_access('accounts:update')
@audit_log('data_modification', 'update', 'compromised_account')
def update_compromised_account(incident_id, account_id):
    """Update a compromised account."""
    incident = g.incident
    data = request.get_json()

    account = CompromisedAccount.query.filter_by(id=account_id, incident_id=incident.id).first()
    if not account:
        return jsonify({'error': 'not_found', 'message': 'Account not found'}), 404

    # Update fields
    for field in ['account_name', 'host_system', 'sid', 'account_type', 'domain',
                  'is_privileged', 'status', 'notes', 'extra_data']:
        if field in data:
            setattr(account, field, data[field])

    if 'datetime_seen' in data:
        account.datetime_seen = parse_datetime(data['datetime_seen'], 'datetime_seen', required=True)

    # Handle host_id
    if 'host_id' in data:
        if data['host_id']:
            host = CompromisedHost.query.filter_by(id=data['host_id'], incident_id=incident.id).first()
            if not host:
                return jsonify({'error': 'bad_request', 'message': 'Invalid host_id'}), 400
            account.host_id = data['host_id']
            account.host_system = host.hostname
        else:
            account.host_id = None

    # Handle timeline_event_id
    if 'timeline_event_id' in data:
        if data['timeline_event_id']:
            event = TimelineEvent.query.filter_by(id=data['timeline_event_id'], incident_id=incident.id).first()
            if not event:
                return jsonify({'error': 'bad_request', 'message': 'Invalid timeline_event_id'}), 400
            account.timeline_event_id = data['timeline_event_id']
        else:
            account.timeline_event_id = None

    # Update password if provided
    if 'password' in data:
        if data['password']:
            try:
                account.password_encrypted = encryption_service.encrypt(data['password'])
            except Exception:
                return jsonify({'error': 'server_error', 'message': 'Failed to encrypt password'}), 500
        else:
            account.password_encrypted = None

    db.session.commit()

    return jsonify(account.to_dict()), 200


@api_bp.route('/incidents/<uuid:incident_id>/accounts/<uuid:account_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('accounts:delete')
@audit_log('data_modification', 'delete', 'compromised_account')
def delete_compromised_account(incident_id, account_id):
    """Delete a compromised account."""
    incident = g.incident

    account = CompromisedAccount.query.filter_by(id=account_id, incident_id=incident.id).first()
    if not account:
        return jsonify({'error': 'not_found', 'message': 'Account not found'}), 404

    db.session.delete(account)
    db.session.commit()

    return jsonify({'message': 'Account deleted'}), 200
