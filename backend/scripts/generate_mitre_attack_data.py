#!/usr/bin/env python3
"""Fetch all MITRE ATT&CK Enterprise techniques and generate kb_data_mitre_attack.py.

Usage:
    python3 backend/scripts/generate_mitre_attack_data.py

This script:
1. Downloads the full ATT&CK Enterprise STIX bundle from MITRE's GitHub CTI repo
2. Extracts all tactics and techniques (including sub-techniques)
3. Maps techniques to their kill-chain phases (tactics)
4. Generates backend/app/api/v1/endpoints/kb_data_mitre_attack.py with comprehensive data

Data source: https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json
"""

import json
import re
import sys
import textwrap
from pathlib import Path

import requests

STIX_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
TIMEOUT = 60  # large JSON, allow ample time

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "api" / "v1" / "endpoints" / "kb_data_mitre_attack.py"
)

# Tactic short-name → display order (kill-chain order)
TACTIC_ORDER = [
    "reconnaissance",
    "resource-development",
    "initial-access",
    "execution",
    "persistence",
    "privilege-escalation",
    "defense-evasion",
    "credential-access",
    "discovery",
    "lateral-movement",
    "collection",
    "command-and-control",
    "exfiltration",
    "impact",
]


def fetch_stix_bundle():
    """Download the full ATT&CK Enterprise STIX bundle."""
    print(f"Downloading ATT&CK Enterprise STIX bundle from GitHub...")
    r = requests.get(STIX_URL, timeout=TIMEOUT)
    r.raise_for_status()
    bundle = r.json()
    print(f"  Bundle contains {len(bundle.get('objects', []))} STIX objects")
    return bundle


def extract_tactics(objects):
    """Extract all tactics (x-mitre-tactic) from the STIX bundle."""
    tactics = []
    for obj in objects:
        if obj.get("type") != "x-mitre-tactic":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue

        ext_refs = obj.get("external_references", [])
        tactic_id = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                tactic_id = ref.get("external_id", "")
                break

        if not tactic_id:
            continue

        short_name = obj.get("x_mitre_shortname", "")
        name = obj.get("name", "")
        description = obj.get("description", "")
        # Clean up description — first sentence only
        description = _clean_description(description)

        tactics.append({
            "id": tactic_id,
            "name": name,
            "short_name": short_name,
            "description": description,
        })

    # Sort by kill-chain order
    def tactic_sort_key(t):
        try:
            return TACTIC_ORDER.index(t["short_name"])
        except ValueError:
            return 999

    tactics.sort(key=tactic_sort_key)
    return tactics


def extract_techniques(objects, tactic_lookup):
    """Extract all techniques and sub-techniques (attack-pattern) from the STIX bundle."""
    techniques = []
    for obj in objects:
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue

        ext_refs = obj.get("external_references", [])
        technique_id = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                technique_id = ref.get("external_id", "")
                break

        if not technique_id:
            continue

        name = obj.get("name", "")
        description = _clean_description(obj.get("description", ""))

        # Platforms
        platforms = obj.get("x_mitre_platforms", [])

        # Kill chain phases → tactic names
        kill_chain_phases = obj.get("kill_chain_phases", [])
        tactic_names = []
        for phase in kill_chain_phases:
            if phase.get("kill_chain_name") == "mitre-attack":
                phase_name = phase.get("phase_name", "")
                tactic_name = tactic_lookup.get(phase_name, phase_name.replace("-", " ").title())
                tactic_names.append(tactic_name)

        # Detection guidance
        detection = _extract_detection(obj)

        # Is it a sub-technique?
        is_sub = obj.get("x_mitre_is_subtechnique", False)

        # For techniques with multiple tactics, we create one entry per tactic
        # to keep backward compatibility with the existing data structure
        if not tactic_names:
            tactic_names = ["Unknown"]

        for tactic_name in tactic_names:
            techniques.append({
                "id": technique_id,
                "name": name,
                "tactic": tactic_name,
                "description": description,
                "platforms": platforms,
                "detection": detection,
                "is_sub": is_sub,
            })

    return techniques


def _clean_description(desc):
    """Clean a STIX description: strip markdown/HTML, first sentence, truncate."""
    if not desc:
        return ""
    # Remove citation references like (Citation: ...)
    desc = re.sub(r"\(Citation:[^)]+\)", "", desc)
    # Remove markdown links [text](url) → text
    desc = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", desc)
    # Remove HTML tags
    desc = re.sub(r"<[^>]+>", "", desc)
    # Collapse whitespace
    desc = re.sub(r"\s+", " ", desc).strip()
    # Take first two sentences max (or first 300 chars)
    sentences = re.split(r'(?<=[.!?])\s+', desc)
    if len(sentences) > 2:
        desc = " ".join(sentences[:2])
    if len(desc) > 300:
        desc = desc[:297] + "..."
    # Escape for Python string
    desc = desc.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return desc


def _extract_detection(obj):
    """Extract detection guidance from a STIX attack-pattern.

    ATT&CK v14+ moved detection into x_mitre_detection or data component refs.
    We prefer x_mitre_detection when available.
    """
    detection = obj.get("x_mitre_detection", "")
    if detection:
        detection = _clean_description(detection)
        if len(detection) > 200:
            detection = detection[:197] + "..."
        return detection
    return ""


def build_tactic_lookup(tactics):
    """Build a short_name → display_name lookup for tactics."""
    return {t["short_name"]: t["name"] for t in tactics}


def generate_python_file(tactics, techniques):
    """Generate the kb_data_mitre_attack.py Python file."""
    # Deduplicate techniques by (id, tactic) — keep first occurrence
    seen = set()
    unique_techniques = []
    for t in techniques:
        key = (t["id"], t["tactic"])
        if key not in seen:
            seen.add(key)
            unique_techniques.append(t)
    techniques = unique_techniques

    # Group techniques by tactic for organized output
    tactic_name_to_short = {t["name"]: t["short_name"] for t in tactics}
    by_tactic = {}
    for t in techniques:
        tactic = t["tactic"]
        if tactic not in by_tactic:
            by_tactic[tactic] = []
        by_tactic[tactic].append(t)

    # Sort techniques within each tactic
    for entries in by_tactic.values():
        entries.sort(key=lambda x: x["id"])

    # Determine tactic display order
    tactic_display_order = [t["name"] for t in tactics]

    lines = []
    lines.append('"""MITRE ATT&CK Enterprise framework reference data.')
    lines.append("")
    lines.append("Auto-generated from MITRE ATT&CK STIX data (https://github.com/mitre/cti).")
    lines.append("Run `python3 backend/scripts/generate_mitre_attack_data.py` to regenerate.")
    lines.append("")
    lines.append("Comprehensive catalogue of all Enterprise tactics and techniques,")
    lines.append("including sub-techniques, with platforms and detection guidance.")
    lines.append('"""')
    lines.append("")

    # Tactics
    lines.append("MITRE_ATTACK_TACTICS = [")
    for t in tactics:
        lines.append(
            f'    {{"id": "{t["id"]}", "name": "{t["name"]}", '
            f'"description": "{t["description"]}"}},',
        )
    lines.append("]")
    lines.append("")

    # Techniques
    lines.append("MITRE_ATTACK_TECHNIQUES = [")
    for tactic_name in tactic_display_order:
        entries = by_tactic.get(tactic_name, [])
        if not entries:
            continue
        # Find tactic ID for comment
        tactic_id = next((t["id"] for t in tactics if t["name"] == tactic_name), "")
        lines.append(f"    # === {tactic_id} — {tactic_name} ===")
        for entry in entries:
            platforms_str = json.dumps(entry["platforms"])
            detection_str = entry["detection"]
            name = entry["name"].replace('"', '\\"')
            lines.append(
                f'    {{"id": "{entry["id"]}", "name": "{name}", '
                f'"tactic": "{entry["tactic"]}", '
                f'"description": "{entry["description"]}", '
                f'"platforms": {platforms_str}, '
                f'"detection": "{detection_str}"}},',
            )
        lines.append("")

    # Handle any tactics not in our predefined order
    for tactic_name, entries in by_tactic.items():
        if tactic_name not in tactic_display_order:
            lines.append(f"    # === {tactic_name} ===")
            for entry in entries:
                platforms_str = json.dumps(entry["platforms"])
                detection_str = entry["detection"]
                name = entry["name"].replace('"', '\\"')
                lines.append(
                    f'    {{"id": "{entry["id"]}", "name": "{name}", '
                    f'"tactic": "{entry["tactic"]}", '
                    f'"description": "{entry["description"]}", '
                    f'"platforms": {platforms_str}, '
                    f'"detection": "{detection_str}"}},',
                )
            lines.append("")

    lines.append("]")
    lines.append("")

    # Derived lookups
    lines.append('MITRE_ATTACK_TACTIC_IDS = {t["id"]: t for t in MITRE_ATTACK_TACTICS}')
    lines.append('MITRE_ATTACK_TECHNIQUE_IDS = {t["id"]: t for t in MITRE_ATTACK_TECHNIQUES}')
    lines.append('MITRE_ATTACK_TACTIC_NAMES = {t["name"]: t for t in MITRE_ATTACK_TACTICS}')
    lines.append("")

    return "\n".join(lines)


def main():
    bundle = fetch_stix_bundle()
    objects = bundle.get("objects", [])

    # Extract tactics
    print("Extracting tactics...")
    tactics = extract_tactics(objects)
    print(f"  Found {len(tactics)} active tactics")
    for t in tactics:
        print(f"    {t['id']} — {t['name']}")

    # Build tactic lookup
    tactic_lookup = build_tactic_lookup(tactics)

    # Extract techniques
    print("Extracting techniques...")
    techniques = extract_techniques(objects, tactic_lookup)
    print(f"  Found {len(techniques)} technique-tactic entries")

    # Stats
    unique_ids = set(t["id"] for t in techniques)
    top_level = {tid for tid in unique_ids if "." not in tid}
    sub_techniques = {tid for tid in unique_ids if "." in tid}
    print(f"  Unique technique IDs: {len(unique_ids)} ({len(top_level)} top-level, {len(sub_techniques)} sub-techniques)")

    # Generate output
    content = generate_python_file(tactics, techniques)
    OUTPUT_PATH.write_text(content)
    print(f"\nGenerated: {OUTPUT_PATH}")
    print(f"File size: {len(content):,} bytes")
    print(f"Techniques in file: {len(techniques)}")


if __name__ == "__main__":
    main()
