"""Defanging/refanging tools for IOC safety."""

from __future__ import annotations

from typing import Optional

from sheetstorm_bridge.client import SheetStormAPIError
from sheetstorm_bridge.server import mcp, get_client


@mcp.tool()
async def sheetstorm_defang_iocs(
    values: Optional[str] = None,
    text: Optional[str] = None,
) -> str:
    """Defang IOC values for safe sharing (e.g. evil.com → evil[.]com).

    Provide either a pipe-separated list of values OR a block of text.

    Args:
        values: Pipe-separated IOC values (e.g. 'evil.com|192.168.1.1|http://bad.site')
        text: Free-form text containing IOCs to defang
    """
    client = get_client()
    try:
        payload: dict = {}
        if values:
            payload["values"] = [v.strip() for v in values.split("|") if v.strip()]
        if text:
            payload["text"] = text
        if not payload:
            return "Provide either 'values' (pipe-separated) or 'text' to defang."

        data = await client.post("/tools/defang", json=payload)

        if data.get("defanged_text"):
            return f"**Defanged Text:**\n{data['defanged_text']}"
        elif data.get("results") or data.get("defanged"):
            results = data.get("results", data.get("defanged", []))
            if isinstance(results, list):
                lines = ["**Defanged IOCs:**"]
                for r in results:
                    if isinstance(r, dict):
                        lines.append(f"  {r.get('original', '?')} → {r.get('defanged', '?')}")
                    else:
                        lines.append(f"  {r}")
                return "\n".join(lines)
            return f"**Defanged:** {results}"
        else:
            return f"Result: {data}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_refang_iocs(
    values: Optional[str] = None,
    text: Optional[str] = None,
) -> str:
    """Refang defanged IOCs back to original form (e.g. evil[.]com → evil.com).

    Provide either a pipe-separated list of values OR a block of text.

    Args:
        values: Pipe-separated defanged IOC values (e.g. 'evil[.]com|192[.]168[.]1[.]1')
        text: Free-form text containing defanged IOCs to refang
    """
    client = get_client()
    try:
        payload: dict = {}
        if values:
            payload["values"] = [v.strip() for v in values.split("|") if v.strip()]
        if text:
            payload["text"] = text
        if not payload:
            return "Provide either 'values' (pipe-separated) or 'text' to refang."

        data = await client.post("/tools/refang", json=payload)

        if data.get("refanged_text"):
            return f"**Refanged Text:**\n{data['refanged_text']}"
        elif data.get("results") or data.get("refanged"):
            results = data.get("results", data.get("refanged", []))
            if isinstance(results, list):
                lines = ["**Refanged IOCs:**"]
                for r in results:
                    if isinstance(r, dict):
                        lines.append(f"  {r.get('original', '?')} → {r.get('refanged', '?')}")
                    else:
                        lines.append(f"  {r}")
                return "\n".join(lines)
            return f"**Refanged:** {results}"
        else:
            return f"Result: {data}"
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
