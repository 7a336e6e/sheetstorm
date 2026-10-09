"""Record-provenance parameters on the timeline / IOC tools (W3-PROV): the
raw timestamp lets the server derive the UTC time, so tools must not invent a
competing timestamp; provenance is echoed back in tool output."""

from __future__ import annotations

import importlib

from conftest import PKG

timeline = importlib.import_module(f"{PKG}.tools.timeline")
iocs = importlib.import_module(f"{PKG}.tools.iocs")

I = "inc-1"  # noqa: E741

PROVENANCE = dict(
    source_evidence_id="ev-1",
    source_artifact_id="art-1",
    source_record_type="evtx_record",
    source_record_ref="Security.evtx EventRecordID=48213",
    raw_timestamp="2026-10-01 14:05:00",
    source_timezone="Europe/Berlin",
    timestamp_type="logged",
    extraction_tool="EvtxECmd",
    extraction_tool_version="1.5.0.0",
)


async def test_create_event_from_raw_timestamp_sends_no_timestamp(client, backend):
    backend.set("POST", f"/incidents/{I}/timeline", {
        "id": "e1", "timestamp": "2026-10-01T12:05:00+00:00", "activity": "logon", "provenance_level": "full",
        "timestamp_derivation": "computed", "clock_skew_applied_seconds": 300,
        "provenance_verified_at": None, **{k: v for k, v in PROVENANCE.items()}})
    out = await timeline.sheetstorm_create_timeline_event(incident_id=I, activity="logon", **PROVENANCE)
    body = backend.find("POST", f"/incidents/{I}/timeline")["json"]
    assert "timestamp" not in body
    assert body == {"activity": "logon", **PROVENANCE}
    assert "Provenance:" in out and "level=full" in out
    assert "record=evtx_record: Security.evtx EventRecordID=48213" in out
    assert "raw=2026-10-01 14:05:00 (Europe/Berlin)" in out
    assert "derivation=computed" in out and "host skew +300s removed" in out and "tool=EvtxECmd 1.5.0.0" in out


async def test_create_event_needs_a_timestamp_or_a_raw_one(client, backend):
    out = await timeline.sheetstorm_create_timeline_event(incident_id=I, activity="x")
    assert out.startswith("✗ Error") and "raw_timestamp" in out
    assert backend.calls == []


async def test_create_event_without_provenance_is_unchanged(client, backend):
    backend.set("POST", f"/incidents/{I}/timeline", {"id": "e1", "timestamp": "2026-01-01T00:00:00Z",
                                                     "activity": "x", "provenance_level": "none"})
    out = await timeline.sheetstorm_create_timeline_event(
        incident_id=I, activity="x", timestamp="2026-01-01T00:00:00Z")
    assert backend.find("POST", f"/incidents/{I}/timeline")["json"] == {
        "activity": "x", "timestamp": "2026-01-01T00:00:00Z"}
    assert "Provenance:" not in out


async def test_update_event_sends_only_provenance_that_was_given(client, backend):
    backend.set("PUT", f"/incidents/{I}/timeline/e1", {"id": "e1", "activity": "x"})
    await timeline.sheetstorm_update_timeline_event(
        incident_id=I, event_id="e1", source_record_ref="a.evtx#2", extraction_tool="Plaso")
    assert backend.find("PUT", f"/incidents/{I}/timeline/e1")["json"] == {
        "source_record_ref": "a.evtx#2", "extraction_tool": "Plaso"}


async def test_add_network_ioc_defaults_now_only_without_a_raw_timestamp(client, backend):
    backend.set("POST", f"/incidents/{I}/network-iocs", {"id": "n1", "dns_ip": "1.2.3.4"})
    await iocs.sheetstorm_add_network_ioc(incident_id=I, dns_ip="1.2.3.4")
    assert "timestamp" in backend.find("POST", f"/incidents/{I}/network-iocs")["json"]

    backend.calls.clear()
    await iocs.sheetstorm_add_network_ioc(
        incident_id=I, dns_ip="1.2.3.4", raw_timestamp="2026-10-01T12:00:00+02:00", source_record_ref="fw.log:4411")
    body = backend.find("POST", f"/incidents/{I}/network-iocs")["json"]
    assert "timestamp" not in body
    assert body["raw_timestamp"] == "2026-10-01T12:00:00+02:00" and body["source_record_ref"] == "fw.log:4411"

    backend.calls.clear()
    await iocs.sheetstorm_add_network_ioc(
        incident_id=I, dns_ip="1.2.3.4", timestamp="2026-10-01T10:00:00Z", raw_timestamp="2026-10-01 12:00",
        source_timezone="Europe/Berlin")
    assert backend.find("POST", f"/incidents/{I}/network-iocs")["json"]["timestamp"] == "2026-10-01T10:00:00Z"


async def test_host_ioc_and_malware_tools_pass_provenance_through(client, backend):
    backend.set("POST", f"/incidents/{I}/host-iocs", {"id": "h1", "artifact_value": "x", "provenance_level": "partial",
                                                     "source_record_ref": "HKLM\\Run"})
    out = await iocs.sheetstorm_add_host_ioc(
        incident_id=I, artifact_type="registry", artifact_value="x", source_record_type="registry_key",
        source_record_ref="HKLM\\Run", source_evidence_id="ev-1")
    body = backend.find("POST", f"/incidents/{I}/host-iocs")["json"]
    assert body["source_record_type"] == "registry_key" and body["source_evidence_id"] == "ev-1"
    assert "record=HKLM\\Run" in out

    backend.set("PUT", f"/incidents/{I}/host-iocs/h1", {"id": "h1", "artifact_value": "x"})
    await iocs.sheetstorm_update_host_ioc(incident_id=I, ioc_id="h1", source_timezone="UTC")
    assert backend.find("PUT", f"/incidents/{I}/host-iocs/h1")["json"] == {"source_timezone": "UTC"}

    backend.set("POST", f"/incidents/{I}/malware", {"id": "m1", "file_name": "evil.exe", "provenance_level": "partial",
                                                    "raw_timestamp": "2026-10-01 12:00"})
    out = await iocs.sheetstorm_add_malware(
        incident_id=I, file_name="evil.exe", raw_timestamp="2026-10-01 12:00", source_timezone="UTC",
        timestamp_type="modified")
    body = backend.find("POST", f"/incidents/{I}/malware")["json"]
    assert body == {"file_name": "evil.exe", "raw_timestamp": "2026-10-01 12:00", "source_timezone": "UTC",
                    "timestamp_type": "modified"}
    assert "raw=2026-10-01 12:00" in out

    backend.set("PUT", f"/incidents/{I}/malware/m1", {"id": "m1", "file_name": "evil.exe"})
    await iocs.sheetstorm_update_malware(incident_id=I, malware_id="m1", extraction_tool="MFTECmd")
    assert backend.find("PUT", f"/incidents/{I}/malware/m1")["json"] == {"extraction_tool": "MFTECmd"}


async def test_provenance_errors_are_reported_not_raised(client, backend):
    backend.set("POST", f"/incidents/{I}/timeline", {
        "error": "timestamp_mismatch", "message": "The timestamp does not match raw_timestamp"}, status=400)
    out = await timeline.sheetstorm_create_timeline_event(
        incident_id=I, activity="x", timestamp="2026-10-01T00:00:00Z", raw_timestamp="2026-10-01 14:00",
        source_timezone="UTC")
    assert out.startswith("✗ Error") and "timestamp" in out
