"""Shared helpers for the record-provenance tool parameters (timeline events,
network / host IOCs, malware). Not a tool module: it registers nothing.

The backend derives the normalized UTC timestamp from ``raw_timestamp`` +
``source_timezone`` (+ the host's clock skew) and rejects a ``timestamp`` that
disagrees with it, so callers either send the raw value and let the server
compute, or send both and make sure they match.
"""

from __future__ import annotations

from typing import Optional

PROVENANCE_PARAMS = (
    "source_evidence_id",
    "source_artifact_id",
    "source_record_type",
    "source_record_ref",
    "raw_timestamp",
    "source_timezone",
    "timestamp_type",
    "extraction_tool",
    "extraction_tool_version",
)


def provenance_payload(**values: Optional[str]) -> dict:
    """The provenance keys that were actually supplied (None = not sent)."""
    return {k: v for k, v in values.items() if k in PROVENANCE_PARAMS and v is not None}


def format_provenance(record: dict) -> list[str]:
    """Output lines for a record's provenance (empty when it has none)."""
    level = record.get("provenance_level")
    if not level or level == "none":
        return []
    parts = [f"level={level}"]
    ref = record.get("source_record_ref")
    if ref:
        rtype = record.get("source_record_type")
        parts.append(f"record={rtype + ': ' if rtype else ''}{ref}")
    if record.get("source_evidence_id"):
        parts.append(f"evidence={record['source_evidence_id']}")
    elif record.get("source_artifact_id"):
        parts.append(f"artifact={record['source_artifact_id']}")
    raw = record.get("raw_timestamp")
    if raw:
        tz = record.get("source_timezone")
        parts.append(f"raw={raw}" + (f" ({tz})" if tz else ""))
    derivation = record.get("timestamp_derivation")
    if derivation:
        parts.append(f"derivation={derivation}")
    skew = record.get("clock_skew_applied_seconds")
    if skew:
        parts.append(f"host skew {skew:+d}s removed")
    tool = record.get("extraction_tool")
    if tool:
        version = record.get("extraction_tool_version")
        parts.append(f"tool={tool}" + (f" {version}" if version else ""))
    verifier = record.get("provenance_verifier")
    if record.get("provenance_verified_at"):
        parts.append(f"verified by {(verifier or {}).get('name') or 'a second analyst'}")
    return ["  Provenance: " + " | ".join(parts)]
