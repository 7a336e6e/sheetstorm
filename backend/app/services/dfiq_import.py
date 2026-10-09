"""Import the DFIQ question library into a running instance (one click).

DFIQ (Digital Forensics Investigative Questions, https://github.com/google/dfiq,
Apache-2.0) is not shipped in the image. A platform administrator imports it
from Admin → Case Templates; the backend then:

1. downloads the archive of ONE pinned commit (``DFIQ_COMMIT``) from GitHub,
   or takes the same archive uploaded by the admin (air-gapped installs);
2. refuses it unless its SHA-256 equals ``DFIQ_ARCHIVE_SHA256`` (supply-chain
   safety: a moved tag, a compromised mirror or a swapped upload never loads);
3. reads only ``dfiq/data/{scenarios,facets,questions}/*.yaml`` plus LICENSE,
   in memory (nothing is extracted to disk; no path is trusted), with size
   caps, ``yaml.safe_load`` and the library's own DFIQ validation;
4. stores the documents in ``system_settings['dfiq_library']`` so every worker
   picks them up (question_library re-reads within 30 s) and they survive
   container rebuilds.

To move to a newer DFIQ commit, update the two pins below after reviewing the
upstream changes (``curl -sL <url> | shasum -a 256``).
"""
import hashlib
import io
import tarfile
from datetime import datetime, timezone

import requests
import yaml

from app.services import question_library
from app.utils.url_validator import validate_outbound_url

DFIQ_COMMIT = 'f07e5f2a5255afda7be9d9de13300d3df12d15f8'  # google/dfiq main, 2026-03-10
DFIQ_ARCHIVE_SHA256 = 'e3bfc0d1de4d53abf8f3c0c362d85770b9940660ac210692cd7d956a2e359ef9'
DFIQ_URL = f'https://codeload.github.com/google/dfiq/tar.gz/{DFIQ_COMMIT}'
DFIQ_REPO_URL = 'https://github.com/google/dfiq'

MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024
MAX_DOCUMENTS = 2000
TIMEOUT_SECONDS = 20
KINDS = ('scenarios', 'facets', 'questions')


class DfiqImportError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def download_archive() -> bytes:
    ok, reason = validate_outbound_url(DFIQ_URL)
    if not ok:
        raise DfiqImportError('url_refused', f'The DFIQ download URL is refused by the outbound URL policy: {reason}', 502)
    try:
        resp = requests.get(DFIQ_URL, timeout=(TIMEOUT_SECONDS, TIMEOUT_SECONDS), stream=True, allow_redirects=False)
    except requests.RequestException as exc:
        raise DfiqImportError('download_failed', f'Could not download DFIQ from GitHub ({type(exc).__name__}). '
                              'On an offline install, upload the archive instead.', 502) from None
    try:
        if resp.status_code != 200:
            raise DfiqImportError('download_failed', f'GitHub answered HTTP {resp.status_code}', 502)
        body = bytearray()
        for chunk in resp.iter_content(chunk_size=65536):
            body.extend(chunk)
            if len(body) > MAX_ARCHIVE_BYTES:
                raise DfiqImportError('archive_too_large', 'The DFIQ archive is larger than expected', 502)
        return bytes(body)
    except requests.RequestException as exc:
        raise DfiqImportError('download_failed', f'DFIQ download interrupted ({type(exc).__name__})', 502) from None
    finally:
        resp.close()


def verify_archive(data: bytes) -> str:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise DfiqImportError('archive_too_large', 'The DFIQ archive is larger than expected')
    digest = hashlib.sha256(data).hexdigest()
    if digest != DFIQ_ARCHIVE_SHA256:
        raise DfiqImportError(
            'integrity_mismatch',
            f'The archive does not match the pinned DFIQ release (SHA-256 {digest[:16]}…, expected '
            f'{DFIQ_ARCHIVE_SHA256[:16]}…). Only the archive of commit {DFIQ_COMMIT[:12]} is accepted.')
    return digest


def parse_archive(data: bytes) -> dict:
    """Documents and license from a verified archive (in memory only)."""
    docs = {k: [] for k in KINDS}
    license_text = ''
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
            for member in tar:
                if not member.isfile():
                    continue  # never follow links / devices
                parts = member.name.split('/')
                if len(parts) == 2 and parts[1] == 'LICENSE' and member.size <= MAX_MEMBER_BYTES:
                    license_text = tar.extractfile(member).read().decode('utf-8', 'replace')
                    continue
                # <top>/dfiq/data/<kind>/<file>.yaml, nothing deeper or elsewhere
                if (len(parts) != 5 or parts[1:3] != ['dfiq', 'data'] or parts[3] not in KINDS
                        or not parts[4].endswith(('.yaml', '.yml'))):
                    continue
                if member.size > MAX_MEMBER_BYTES:
                    raise DfiqImportError('invalid_archive', f'{parts[4]}: file too large')
                raw = tar.extractfile(member).read()
                try:
                    doc = yaml.safe_load(raw)
                except yaml.YAMLError as exc:
                    raise DfiqImportError('invalid_archive', f'{parts[4]}: invalid YAML ({exc})') from None
                docs[parts[3]].append(
                    question_library.check_dfiq_doc(doc, f'dfiq/{parts[3]}/{parts[4]}'))
                if sum(len(v) for v in docs.values()) > MAX_DOCUMENTS:
                    raise DfiqImportError('invalid_archive', 'Too many DFIQ documents')
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise DfiqImportError('invalid_archive', f'Not a readable DFIQ archive ({type(exc).__name__})') from None
    except question_library.LibraryError as exc:
        raise DfiqImportError('invalid_archive', str(exc)) from None
    for kind in KINDS:
        docs[kind].sort(key=lambda d: d['id'])
    try:
        index, groups = question_library.dfiq_from_docs(docs['scenarios'], docs['facets'], docs['questions'])
    except question_library.LibraryError as exc:
        raise DfiqImportError('invalid_archive', str(exc)) from None
    if not index:
        raise DfiqImportError('invalid_archive', 'The archive contains no DFIQ questions')
    return {**docs, 'license': license_text, 'counts': {
        'scenarios': len(groups), 'facets': sum(len(g['facets']) for g in groups), 'questions': len(index)}}


def build_document(data: bytes, digest: str, actor, method: str) -> dict:
    parsed = parse_archive(data)
    return {
        'commit': DFIQ_COMMIT,
        'sha256': digest,
        'source': DFIQ_REPO_URL,
        'method': method,  # 'download' | 'upload'
        'imported_at': datetime.now(timezone.utc).isoformat(),
        'imported_by': {'id': str(actor.id), 'name': actor.name} if actor else None,
        **parsed,
    }


def status(row) -> dict:
    value = row.value if row is not None else None
    return {
        'imported': bool(value),
        'commit': value.get('commit') if value else None,
        'sha256': value.get('sha256') if value else None,
        'method': value.get('method') if value else None,
        'imported_at': value.get('imported_at') if value else None,
        'imported_by': value.get('imported_by') if value else None,
        'counts': value.get('counts') if value else None,
        'version': row.version if row is not None else 0,
        'pinned_commit': DFIQ_COMMIT,
        'pinned_sha256': DFIQ_ARCHIVE_SHA256,
        'download_url': DFIQ_URL,
        'source': DFIQ_REPO_URL,
        'license': 'Apache-2.0',
        'attribution': question_library.DFIQ_SOURCE['attribution'],
        'vendored_files': bool(question_library._load_dfiq(question_library.DFIQ_DIR)[0]),
    }
