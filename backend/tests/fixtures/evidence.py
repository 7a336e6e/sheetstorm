"""Evidence register / custody ledger fixtures (W1-EVD-CORE).

- ``make_evidence(incident, actor=None, register=True, **fields)``: an
  EvidenceItem numbered + registered through ``CustodyLedger`` (``register``
  entry). ``register=False`` inserts a bare item (no ledger entry) so a test
  can add legacy rows before the first chained entry.
- ``make_artifact(incident, item=None, actor=None, upload_entry=True, **fields)``:
  a stored-file artifact on ``item`` (a new registered item when omitted) plus
  its ``upload`` entry.
- ``insert_legacy_custody(artifact, **fields)``: a pre-v3 (unchained) custody
  row written with raw SQL, as rows written before the upgrade look.
- ``ledger_tamper()``: context manager that disables the append-only
  triggers so a test can simulate a DB-level attacker (UPDATE/DELETE rows).
"""
import contextlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

_TAMPER_TRIGGERS = (('chain_of_custody', 'coc_append_only'), ('custody_anchors', 'anchors_append_only'))


@pytest.fixture
def make_evidence(app, db, users):
    from app.models import EvidenceItem
    from app.services.custody_ledger import CustodyLedger

    def make(incident, actor=None, register=True, **fields):
        actor = actor or users['Administrator']
        item = EvidenceItem(incident_id=incident.id, organization_id=incident.organization_id,
                            evidence_type=fields.pop('evidence_type', 'disk_image'),
                            title=fields.pop('title', f'Item {uuid.uuid4().hex[:6]}'),
                            created_by=actor.id, **fields)
        if register:
            CustodyLedger.register_item(item, actor=actor)
        else:
            from sqlalchemy import func
            last = db.session.query(func.max(EvidenceItem.sequence_number)).filter(
                EvidenceItem.incident_id == incident.id).scalar()
            item.sequence_number = (last or 0) + 1
            db.session.add(item)
        db.session.commit()
        return item
    return make


@pytest.fixture
def make_artifact(app, db, users, make_evidence):
    from app.models import Artifact
    from app.services.chain_of_custody_service import ChainOfCustodyService

    def make(incident, item=None, actor=None, upload_entry=True, **fields):
        actor = actor or users['Administrator']
        item = item or make_evidence(incident, actor=actor, evidence_type='digital_file')
        name = fields.pop('original_filename', 'evidence.bin')
        a = Artifact(incident_id=incident.id, evidence_item_id=item.id, filename=fields.pop('filename', 'f.bin'),
                     original_filename=name, storage_path=fields.pop('storage_path', 'x'),
                     storage_type=fields.pop('storage_type', 'local'), file_size=fields.pop('file_size', 3),
                     md5=fields.pop('md5', '0' * 32), sha256=fields.pop('sha256', '0' * 64),
                     sha512=fields.pop('sha512', '0' * 128), uploaded_by=actor.id, **fields)
        db.session.add(a)
        db.session.flush()
        if upload_entry:
            ChainOfCustodyService.log_upload(a, actor, 'pytest', commit=False)
        db.session.commit()
        return a
    return make


@pytest.fixture
def insert_legacy_custody(app, db, users):
    def insert(artifact, action='download', performed_by=None, created_at=None, signature=None,
               signature_key_id=None, **fields):
        rid = fields.get('id') or uuid.uuid4()
        db.session.execute(text(
            'INSERT INTO chain_of_custody (id, artifact_id, evidence_item_id, incident_id, action, performed_by, '
            'ip_address, user_agent, purpose, verification_result, extra_data, signature, signature_key_id, '
            'created_at) VALUES (:id, :a, :e, :i, :act, :p, :ip, :ua, :purpose, :vr, CAST(:ed AS jsonb), :sig, '
            ':kid, :ts)'), {
            'id': rid, 'a': artifact.id, 'e': artifact.evidence_item_id, 'i': artifact.incident_id,
            'act': action, 'p': (performed_by or users['Administrator']).id,
            'ip': fields.get('ip_address', '10.0.0.5'), 'ua': fields.get('user_agent', 'pytest-agent'),
            'purpose': fields.get('purpose'), 'vr': fields.get('verification_result'),
            'ed': fields.get('extra_data_json', '{}'), 'sig': signature, 'kid': signature_key_id,
            'ts': created_at or datetime.now(timezone.utc)})
        db.session.commit()
        return rid
    return insert


@pytest.fixture
def ledger_tamper(app, db):
    @contextlib.contextmanager
    def tamper():
        for table, trigger in _TAMPER_TRIGGERS:
            db.session.execute(text(f'ALTER TABLE {table} DISABLE TRIGGER {trigger}'))
        try:
            yield db.session
            db.session.commit()
        finally:
            db.session.rollback()
            for table, trigger in _TAMPER_TRIGGERS:
                db.session.execute(text(f'ALTER TABLE {table} ENABLE TRIGGER {trigger}'))
            db.session.commit()
    return tamper
