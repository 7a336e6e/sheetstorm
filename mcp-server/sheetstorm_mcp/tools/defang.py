"""IOC defanging/refanging tools — safely share indicators of compromise."""

from __future__ import annotations

from typing import Optional

from sheetstorm_mcp.client import SheetStormAPIError
from sheetstorm_mcp.server import mcp, get_client


@mcp.tool()
async def sheetstorm_defang_iocs(
    values: Optional[list[str]] = None,
    text: Optional[str] = None,
    ioc_type: str = "auto",
) -> str:
    """Defang IOCs for safe sharing — converts active indicators to inert text.

    Examples:
      evil.com   → evil[.]com
      http://     → hxxp://
      1.2.3.4    → 1[.]2[.]3[.]4
      user@e.com → user[@]e[.]com

    Provide EITHER a list of individual values OR a free-text block.

    Args:
        values: List of IOC strings to defang individually
        text: A block of text containing IOCs to defang in-place
        ioc_type: Type hint for individual values — auto, ip, domain, url, email (default auto)
    """
    client = get_client()
    try:
        payload: dict = {}
        if values:
            payload["values"] = values
            payload["type"] = ioc_type
        elif text:
            payload["text"] = text
        else:
            return "✗ Provide either 'values' (list) or 'text' (string)."

        data = await client.post("/tools/defang", json=payload)

        # Individual values mode
        items = data.get("items")
        if items:
            lines = [f"**Defanged IOCs** ({len(items)} items)\n"]
            for item in items:
                lines.append(f"  {item['original']}  →  {item['defanged']}")
            return "\n".join(lines)

        # Text mode
        if "defanged" in data:
            return f"**Defanged text**:\n{data['defanged']}"

        return "✗ Unexpected response."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"


@mcp.tool()
async def sheetstorm_refang_iocs(
    values: Optional[list[str]] = None,
    text: Optional[str] = None,
) -> str:
    """Refang IOCs — convert defanged indicators back to active form.

    Examples:
      evil[.]com → evil.com
      hxxp://    → http://

    Provide EITHER a list of individual values OR a free-text block.

    Args:
        values: List of defanged IOC strings to refang
        text: A block of defanged text to refang in-place
    """
    client = get_client()
    try:
        payload: dict = {}
        if values:
            payload["values"] = values
        elif text:
            payload["text"] = text
        else:
            return "✗ Provide either 'values' (list) or 'text' (string)."

        data = await client.post("/tools/refang", json=payload)

        items = data.get("items")
        if items:
            lines = [f"**Refanged IOCs** ({len(items)} items)\n"]
            for item in items:
                lines.append(f"  {item['defanged']}  →  {item['original']}")
            return "\n".join(lines)

        if "original" in data:
            return f"**Refanged text**:\n{data['original']}"

        return "✗ Unexpected response."
    except SheetStormAPIError as exc:
        return f"✗ Error: {exc}"
