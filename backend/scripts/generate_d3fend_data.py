#!/usr/bin/env python3
"""Fetch all D3FEND techniques from MITRE's API and generate kb_data_d3fend.py.

Usage:
    python3 backend/scripts/generate_d3fend_data.py

This script:
1. Fetches all D3FEND technique IDs from https://d3fend.mitre.org/api/technique/all.json
2. For each technique, fetches detailed ATT&CK mappings, tactic, and description
3. Generates backend/app/api/v1/endpoints/kb_data_d3fend.py with comprehensive data
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://d3fend.mitre.org/api/technique"
TIMEOUT = 15
DELAY = 0.25  # seconds between requests to be polite

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "api" / "v1" / "endpoints" / "kb_data_d3fend.py"

# ── Manual Overrides ──────────────────────────────────────────────────────────
# Some ATT&CK techniques have ZERO official D3FEND mappings in MITRE's database.
# We manually assign them to the most relevant existing D3FEND techniques here
# so that every ATT&CK TTP observed in incidents gets at least one countermeasure.
# Format: D3FEND-ID → list of ATT&CK technique IDs to inject.
MANUAL_ATTACK_OVERRIDES: dict[str, list[str]] = {
    # T1046 — Network Service Discovery (port scanning, service enumeration)
    "D3-NTA":  ["T1046"],  # Network Traffic Analysis — detect scanning patterns
    "D3-CAA":  ["T1046"],  # Connection Attempt Analysis — detect port probes
    "D3-NTCD": ["T1046"],  # Network Traffic Community Deviation — anomalous scanning
    "D3-NTSA": ["T1046"],  # Network Traffic Signature Analysis — known scan signatures

    # T1069 — Permission Groups Discovery (enumerating domain/local groups)
    "D3-UBA":  ["T1069"],  # User Behavior Analysis — detect unusual enumeration
    "D3-PSA":  ["T1069", "T1569"],  # Process Spawn Analysis — detect enumeration/service cmds
    "D3-SCA":  ["T1069", "T1569"],  # System Call Analysis — detect group-query/service syscalls

    # T1485 — Data Destruction (deleting/wiping data)
    "D3-RF":   ["T1485", "T1486", "T1490"],  # Restore File — recover destroyed/encrypted files
    "D3-RD":   ["T1485", "T1486"],  # Restore Database — recover destroyed/encrypted DBs
    "D3-FIM":  ["T1485", "T1486"],  # File Integrity Monitoring — detect mass file changes
    "D3-HBWP": ["T1485"],  # Hardware-based Write Protection — prevent data wipes

    # T1486 — Data Encrypted for Impact (ransomware)
    # (Covered above via D3-RF, D3-RD, D3-FIM)
    "D3-FCA":  ["T1486"],  # File Creation Analysis — detect mass .encrypted file creation

    # T1490 — Inhibit System Recovery (deleting backups, disabling recovery)
    # (D3-RF covered above)
    "D3-RC":   ["T1490"],  # Restore Configuration — restore system/boot configuration
    "D3-RS":   ["T1490"],  # Restore Software — restore recovery software/tools
    "D3-SFA":  ["T1490", "T1569"],  # System File Analysis — detect recovery tool deletion

    # T1569 — System Services (abusing services for execution)
    # (D3-PSA, D3-SCA, D3-SFA covered above)

    # T1595 — Active Scanning (port scanning, vulnerability scanning from external)
    # D3-NTA, D3-NTSA, D3-NTCD, D3-CAA already exist above for T1046; append T1595 family
    # (handled by extending existing keys below)

    # T1589 — Gather Victim Identity Information (OSINT on credentials, emails, names)
    "D3-SMRA": ["T1589"],  # Sender MTA Reputation Analysis — detect spoofed identity reuse
    "D3-MA":   ["T1589"],  # Message Analysis — detect phishing using harvested identities

    # T1489 — Service Stop (stopping critical services for impact)
    "D3-OSM":  ["T1489"],  # Operating System Monitoring — detect service state changes
    "D3-SDM":  ["T1489"],  # System Daemon Monitoring — detect daemon termination
    "D3-PA":   ["T1489"],  # Process Analysis — detect service process kill
}

# Extend existing override keys with additional ATT&CK technique families.
# This avoids overwriting the original lists defined above.
_EXTENSIONS: dict[str, list[str]] = {
    # T1595 (Active Scanning) shares the same D3FEND countermeasures as T1046
    "D3-NTA":  ["T1595", "T1595.001", "T1595.002"],
    "D3-CAA":  ["T1595", "T1595.001", "T1595.002"],
    "D3-NTCD": ["T1595", "T1595.001", "T1595.002"],
    "D3-NTSA": ["T1595", "T1595.001", "T1595.002"],
    "D3-ISVA": ["T1595", "T1595.001", "T1595.002"],  # Inbound Session Volume Analysis
    "D3-PMAD": ["T1595", "T1595.001", "T1595.002"],  # Protocol Metadata Anomaly Detection

    # T1589 (Gather Victim Identity) — detection/monitoring overlaps
    "D3-UBA":  ["T1589", "T1589.001", "T1589.002"],
    "D3-SRA":  ["T1589", "T1589.001", "T1589.002"],  # Sender Reputation Analysis

    # T1489 (Service Stop) — system monitoring overlaps
    "D3-SFA":  ["T1489"],  # System File Analysis — detect service binary deletion
    "D3-PSA":  ["T1489"],  # Process Spawn Analysis — detect service-killing commands
}

# Merge extensions into MANUAL_ATTACK_OVERRIDES
for _key, _ids in _EXTENSIONS.items():
    if _key in MANUAL_ATTACK_OVERRIDES:
        MANUAL_ATTACK_OVERRIDES[_key].extend(_ids)
    else:
        MANUAL_ATTACK_OVERRIDES[_key] = _ids


def fetch_all_technique_ids():
    """Get list of all D3FEND techniques from the bulk endpoint."""
    r = requests.get(f"{API_BASE}/all.json", timeout=TIMEOUT)
    r.raise_for_status()
    graph = r.json()["@graph"]
    techniques = []
    for item in graph:
        d3fend_id = item.get("d3f:d3fend-id", "")
        label = item.get("rdfs:label", "")
        class_name = item["@id"].replace("d3f:", "")
        if d3fend_id and label:
            techniques.append({
                "d3fend_id": d3fend_id,
                "label": label,
                "class_name": class_name,
            })
    return techniques


def fetch_technique_detail(class_name):
    """Fetch detailed info for a single D3FEND technique."""
    url = f"{API_BASE}/d3f:{class_name}.json"
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    return r.json()


def extract_attack_mappings(detail):
    """Extract unique ATT&CK technique IDs from the def_to_off bindings."""
    bindings = detail.get("def_to_off", {}).get("results", {}).get("bindings", [])
    attack_ids = set()
    for b in bindings:
        off_tech_id = b.get("off_tech_id", {}).get("value", "")
        if off_tech_id and re.match(r"T\d{4}", off_tech_id):
            attack_ids.add(off_tech_id)
    return sorted(attack_ids)


def extract_tactic(detail):
    """Extract the D3FEND tactic from bindings."""
    bindings = detail.get("def_to_off", {}).get("results", {}).get("bindings", [])
    for b in bindings:
        tactic = b.get("def_tactic_label", {}).get("value", "")
        if tactic:
            return tactic
    return ""


def extract_description(detail):
    """Extract technique description from D3FEND API response.
    
    The description field contains an RDF @graph with a d3f:definition key.
    """
    desc_data = detail.get("description", "")
    
    # The description is an RDF graph structure
    if isinstance(desc_data, dict):
        graph = desc_data.get("@graph", [])
        for node in graph:
            definition = node.get("d3f:definition", "")
            if definition:
                desc = definition
                break
        else:
            desc = ""
    elif isinstance(desc_data, str):
        desc = desc_data
    else:
        desc = ""
    
    # Clean up any HTML tags
    desc = re.sub(r"<[^>]+>", "", str(desc)).strip()
    # Remove newlines and excessive whitespace
    desc = re.sub(r"\s+", " ", desc).strip()
    # Escape backslashes first, then quotes  
    desc = desc.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    # Truncate long descriptions
    if len(desc) > 250:
        desc = desc[:247] + "..."
    return desc


def normalize_top_level(attack_ids):
    """Extract top-level technique IDs (T1234) from sub-technique IDs (T1234.001).
    
    Returns both: full sub-technique IDs for precision AND top-level parents.
    For the mapping file we store top-level IDs so that lookups on either
    T1090 or T1090.001 will match.
    """
    top_level = set()
    for tid in attack_ids:
        # Always include the full ID
        top_level.add(tid)
        # Also include the parent technique
        parent = tid.split(".")[0]
        top_level.add(parent)
    return sorted(top_level)


def generate_python_file(techniques_data):
    """Generate the kb_data_d3fend.py file content."""
    # Group by tactic
    tactic_order = ["Harden", "Detect", "Isolate", "Deceive", "Evict", "Restore", "Model"]
    by_tactic = {}
    for t in techniques_data:
        tactic = t["tactic"]
        if tactic not in by_tactic:
            by_tactic[tactic] = []
        by_tactic[tactic].append(t)

    lines = [
        '"""MITRE D3FEND countermeasure reference data.',
        "",
        "Auto-generated from MITRE D3FEND API (https://d3fend.mitre.org).",
        "Run `python3 backend/scripts/generate_d3fend_data.py` to regenerate.",
        "",
        "Comprehensive catalogue of defensive techniques mapped to ATT&CK techniques,",
        "organized by D3FEND tactic.",
        '"""',
        "",
        "D3FEND_TECHNIQUES = [",
    ]

    for tactic in tactic_order:
        entries = by_tactic.get(tactic, [])
        if not entries:
            continue
        entries.sort(key=lambda x: x["id"])
        lines.append(f"    # === {tactic} ===")
        for entry in entries:
            attack_list = json.dumps(entry["attack_mappings"])
            desc = entry["description"]
            name = entry["name"].replace('"', '\\"')
            lines.append(
                f'    {{"id": "{entry["id"]}", "name": "{name}", '
                f'"tactic": "{tactic}", '
                f'"description": "{desc}", '
                f'"mitre_attack_mappings": {attack_list}}},',
            )
        lines.append("")

    # Handle any tactics not in our predefined order
    for tactic, entries in by_tactic.items():
        if tactic not in tactic_order:
            entries.sort(key=lambda x: x["id"])
            lines.append(f"    # === {tactic} ===")
            for entry in entries:
                attack_list = json.dumps(entry["attack_mappings"])
                desc = entry["description"]
                name = entry["name"].replace('"', '\\"')
                lines.append(
                    f'    {{"id": "{entry["id"]}", "name": "{name}", '
                    f'"tactic": "{tactic}", '
                    f'"description": "{desc}", '
                    f'"mitre_attack_mappings": {attack_list}}},',
                )
            lines.append("")

    lines.append("]")
    lines.append("")
    lines.append('D3FEND_TACTICS = sorted(set(t["tactic"] for t in D3FEND_TECHNIQUES))')
    lines.append('D3FEND_TECHNIQUE_IDS = {t["id"]: t for t in D3FEND_TECHNIQUES}')
    lines.append("")

    return "\n".join(lines)


def main():
    print("Fetching all D3FEND technique IDs...")
    all_techniques = fetch_all_technique_ids()
    print(f"Found {len(all_techniques)} D3FEND techniques")

    techniques_data = []
    skipped = 0
    errors = 0

    for i, tech in enumerate(all_techniques):
        d3fend_id = tech["d3fend_id"]
        label = tech["label"]
        class_name = tech["class_name"]

        if i % 20 == 0:
            print(f"  Processing {i+1}/{len(all_techniques)} ({label})...")

        try:
            detail = fetch_technique_detail(class_name)
            if not detail:
                skipped += 1
                continue

            attack_ids = extract_attack_mappings(detail)
            tactic = extract_tactic(detail)
            description = extract_description(detail)

            if not attack_ids:
                # No ATT&CK mappings — skip
                skipped += 1
                continue

            if not tactic:
                # Try to infer tactic from parent/context
                tactic = "Detect"  # Default fallback

            # Normalize to include both sub-technique and parent IDs
            attack_ids = normalize_top_level(attack_ids)

            techniques_data.append({
                "id": d3fend_id,
                "name": label,
                "tactic": tactic,
                "description": description or f"D3FEND defensive technique: {label}.",
                "attack_mappings": attack_ids,
            })
        except Exception as e:
            errors += 1
            print(f"  ERROR fetching {class_name}: {e}")

        time.sleep(DELAY)

    print(f"\nResults: {len(techniques_data)} techniques with ATT&CK mappings, {skipped} skipped (no mappings), {errors} errors")

    # ── Apply manual overrides ────────────────────────────────────────────
    injected_count = 0
    tech_by_id = {t["id"]: t for t in techniques_data}
    for d3fend_id, extra_attack_ids in MANUAL_ATTACK_OVERRIDES.items():
        entry = tech_by_id.get(d3fend_id)
        if entry is None:
            print(f"  WARNING: Manual override target {d3fend_id} not found — skipping")
            continue
        existing = set(entry["attack_mappings"])
        for tid in extra_attack_ids:
            if tid not in existing:
                existing.add(tid)
                injected_count += 1
        entry["attack_mappings"] = sorted(existing)
    print(f"Manual overrides: injected {injected_count} extra ATT&CK IDs into {len(MANUAL_ATTACK_OVERRIDES)} D3FEND entries")

    # Generate coverage stats
    all_attack_ids = set()
    for t in techniques_data:
        all_attack_ids.update(t["attack_mappings"])
    top_level_ids = {tid for tid in all_attack_ids if "." not in tid}
    print(f"Total unique ATT&CK IDs covered: {len(all_attack_ids)} ({len(top_level_ids)} top-level)")

    # Generate the file
    content = generate_python_file(techniques_data)
    OUTPUT_PATH.write_text(content)
    print(f"\nGenerated: {OUTPUT_PATH}")
    print(f"File size: {len(content)} bytes")


if __name__ == "__main__":
    main()
