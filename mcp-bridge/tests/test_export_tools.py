"""W3-DFIR-C MCP tools: CSV export, STIX save, report snapshots, graph merge."""

from __future__ import annotations

import importlib

import httpx
from conftest import PKG

advanced = importlib.import_module(f"{PKG}.tools.advanced_analysis")
reports = importlib.import_module(f"{PKG}.tools.reports")
graph = importlib.import_module(f"{PKG}.tools.attack_graph")

I = "inc-1"  # noqa: E741
CSV = "﻿Hostname,Notes\r\nws-01,ok\r\n'=cmd,\"a,b\"\r\n"


async def test_export_csv_inline_returns_rows_and_a_note(client, backend):
    backend.set("GET", f"/incidents/{I}/export/hosts", CSV)
    out = await advanced.sheetstorm_export_csv(incident_id=I, entity="hosts", filters_json='{"q": "ws"}')
    assert "ws-01,ok" in out and "2 rows" in out and "﻿" not in out
    assert backend.find("GET", f"/incidents/{I}/export/hosts")["params"] == {"q": "ws"}


async def test_export_csv_truncates_inline_at_200_rows(client, backend):
    body = "H\r\n" + "".join(f"r{i}\r\n" for i in range(250))
    backend.set("GET", f"/incidents/{I}/export/timeline", body)
    out = await advanced.sheetstorm_export_csv(incident_id=I, entity="timeline")
    assert "r199" in out and "r200" not in out
    assert "first 200 of 250 rows" in out and "save_path" in out


async def test_export_csv_saves_the_complete_file(client, backend, tmp_path):
    backend.set("GET", f"/incidents/{I}/export/network-iocs", CSV)
    target = tmp_path / "iocs.csv"
    out = await advanced.sheetstorm_export_csv(incident_id=I, entity="network-iocs", save_path=str(target),
                                               defang=True)
    assert "saved" in out and target.read_bytes() == CSV.encode()
    assert backend.find("GET", f"/incidents/{I}/export/network-iocs")["params"]["defang"] == "true"


async def test_export_csv_validates_input_before_any_request(client, backend):
    assert "entity must be one of" in await advanced.sheetstorm_export_csv(incident_id=I, entity="passwords")
    assert "JSON object" in await advanced.sheetstorm_export_csv(incident_id=I, entity="hosts", filters_json="[1]")
    assert "JSON" in await advanced.sheetstorm_export_csv(incident_id=I, entity="hosts", filters_json="{nope")
    assert "simple values" in await advanced.sheetstorm_export_csv(incident_id=I, entity="hosts",
                                                                   filters_json='{"a": {"b": 1}}')
    assert backend.calls == []


async def test_export_csv_reports_the_permission_error(client, backend):
    backend.set("GET", f"/incidents/{I}/export/hosts",
                {"error": "forbidden", "message": "Permission denied. Required: incidents:export"}, status=403)
    out = await advanced.sheetstorm_export_csv(incident_id=I, entity="hosts")
    assert out.startswith("✗") and "incidents:export" in out


async def test_export_stix_can_save_the_full_bundle(client, backend, tmp_path):
    bundle = {"type": "bundle", "id": "bundle--1", "objects": [{"type": "report", "name": "R", "labels": ["high"],
                                                                "object_refs": ["a"]}]}
    backend.set("GET", f"/incidents/{I}/export/stix", bundle)
    target = tmp_path / "b.json"
    out = await advanced.sheetstorm_export_stix(incident_id=I, save_path=str(target))
    assert "bundle--1" in out and "saved" in out and b'"bundle--1"' in target.read_bytes()
    out = await advanced.sheetstorm_export_stix(incident_id=I)
    assert "save_path" in out


async def test_correlate_with_incident_id_excludes_that_incident(client, backend):
    backend.set("POST", "/correlate-iocs", {"correlations": [{
        "ioc_value": "evil.example", "ioc_type": "network_ioc", "incident_count": 2,
        "incidents": [{"id": "inc-1", "title": "This one"}, {"id": "inc-2-xxxxxxxx", "title": "Other"}]}]})
    out = await advanced.sheetstorm_correlate_iocs(incident_id=I)
    assert "Other" in out and "This one" not in out and "Also seen in **1**" in out
    assert backend.find("POST", "/correlate-iocs")["json"] == {"incident_id": I}


async def test_bulk_enrich_shows_providers_and_blocked(client, backend):
    backend.set("POST", "/bulk-enrich", {
        "total": 2, "enriched": 1, "failed": 0, "blocked": 1, "providers": ["virustotal"],
        "results": [{"type": "domain", "value": "a.example", "status": "success",
                     "enrichment": {"virustotal": {"malicious": 3}}},
                    {"type": "domain", "value": "b.example", "status": "blocked", "error": "tlp_restricted"}]})
    out = await advanced.sheetstorm_bulk_enrich(ioc_values="domain:a.example|domain:b.example", incident_id=I)
    assert "Providers: virustotal" in out and "Blocked (TLP): 1" in out and "tlp_restricted" in out


async def test_generate_pdf_report_handles_the_binary_snapshot(client, backend, tmp_path, monkeypatch):
    sent = {}

    async def fake_send(method, path, **kw):
        sent.update(method=method, path=path, **kw)
        return httpx.Response(200, content=b"%PDF-1.7 fake", headers={
            "content-type": "application/pdf", "X-Report-SHA256": "ab" * 32, "X-Report-Id": "rep-1",
            "X-SheetStorm-AI-Status": "ai_blocked_by_tlp"})
    monkeypatch.setattr(client, "_send", fake_send)
    target = tmp_path / "r.pdf"
    out = await reports.sheetstorm_generate_pdf_report(incident_id=I, report_type="ioc", save_path=str(target))
    assert sent["method"] == "POST" and sent["json"] == {"report_type": "ioc"}
    assert "Report ID: rep-1" in out and ("ab" * 32) in out and "data-only" in out and "Saved to" in out
    assert target.read_bytes() == b"%PDF-1.7 fake"
    out = await reports.sheetstorm_generate_pdf_report(incident_id=I)
    assert "Pass save_path" in out


async def test_list_reports_shows_the_hash_and_snapshot_flag(client, backend):
    backend.set("GET", f"/incidents/{I}/reports", {"items": [
        {"id": "r1", "title": "Snap", "report_type": "full", "format": "pdf", "is_snapshot": True,
         "sha256": "cd" * 32, "size_bytes": 1234},
        {"id": "r2", "title": "Old", "report_type": "full", "format": "pdf", "is_snapshot": False}]})
    out = await reports.sheetstorm_list_reports(incident_id=I)
    assert ("cd" * 32) in out and "1234 bytes" in out and "legacy report" in out


async def test_auto_generate_graph_sends_mode_and_confirm(client, backend):
    backend.set("POST", f"/incidents/{I}/attack-graph/auto-generate",
                {"mode": "merge", "created": {"nodes": 2, "edges": 3}, "nodes": [], "edges": []})
    out = await graph.sheetstorm_auto_generate_graph(incident_id=I)
    assert "2 nodes, 3 edges" in out and "merge" in out
    assert backend.find("POST", f"/incidents/{I}/attack-graph/auto-generate")["json"] == {"mode": "merge"}
    backend.set("POST", f"/incidents/{I}/attack-graph/auto-generate",
                {"error": "confirmation_required", "message": "send confirm"}, status=400)
    out = await graph.sheetstorm_auto_generate_graph(incident_id=I, mode="replace")
    assert out.startswith("✗") and "confirm" in out
