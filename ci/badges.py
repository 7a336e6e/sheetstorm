#!/usr/bin/env python3
"""README badges as plain SVG files in assets/badges/ (no third-party badge
service: they always render, in every browser, and leak no README views).

    python3 ci/badges.py           # write the badges
    python3 ci/badges.py --check   # fail when a badge is stale (CI)

Every value comes from the repository itself:
  release     latest "## X.Y.Z" section of CHANGELOG.md
  license     LICENSE
  Next.js     frontend/package.json ("next", major)
  Flask       backend/requirements.txt (major.minor)
  PostgreSQL  database/Dockerfile (postgres image tag)
  MCP         number of @mcp.tool / @server.tool decorators in mcp-server
The CI badge is GitHub's own workflow badge (dynamic), referenced in README.md.
"""
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets' / 'badges'

LABEL_COLOR = '#555'
BRAND = '#4D82CB'
DARK = '#30363D'

# Approximate Verdana 11px advance widths (px); textLength makes the
# rendered text fit exactly, so small errors only change the padding.
_NARROW = {'i': 3.0, 'l': 3.0, 'j': 3.4, '.': 3.5, ',': 3.5, ':': 4.0, ' ': 3.9, 'f': 3.9, 't': 4.3,
           'r': 4.7, 'I': 4.6, '1': 7.0, '-': 4.6, '(': 4.5, ')': 4.5}
_WIDE = {'m': 9.7, 'w': 8.2, 'M': 9.0, 'W': 10.1, 'Q': 8.5, 'G': 8.4, 'O': 8.5, 'D': 8.4, 'C': 7.7, 'N': 8.4}


def text_width(text):
    total = 0.0
    for ch in text:
        if ch in _NARROW:
            total += _NARROW[ch]
        elif ch in _WIDE:
            total += _WIDE[ch]
        elif ch.isdigit():
            total += 7.0
        elif ch.isupper():
            total += 7.5
        else:
            total += 6.2
    return round(total)


def badge_svg(label, value, color):
    """A flat-square badge, 20 px high (the shields.io layout)."""
    lt, vt = text_width(label), text_width(value)
    lw, vw = lt + 10, vt + 10
    w = lw + vw
    title = escape(f'{label}: {value}')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{title}">'
        f'<title>{title}</title>'
        f'<g shape-rendering="crispEdges"><rect width="{lw}" height="20" fill="{LABEL_COLOR}"/>'
        f'<rect x="{lw}" width="{vw}" height="20" fill="{color}"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        f'text-rendering="geometricPrecision" font-size="110">'
        f'<text x="{lw * 5}" y="140" transform="scale(.1)" textLength="{lt * 10}">{escape(label)}</text>'
        f'<text x="{lw * 10 + vw * 5}" y="140" transform="scale(.1)" textLength="{vt * 10}">{escape(value)}</text>'
        f'</g></svg>\n'
    )


def released_version():
    for line in (ROOT / 'CHANGELOG.md').read_text().splitlines():
        m = re.match(r'^## \[?v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?(?:\s|$)', line)
        if m:
            return m.group(1)
    raise SystemExit('badges: no released "## X.Y.Z" section in CHANGELOG.md')


def license_name():
    first = (ROOT / 'LICENSE').read_text().splitlines()[0]
    return first.replace('License', '').strip() or first


def next_major():
    deps = json.loads((ROOT / 'frontend' / 'package.json').read_text())['dependencies']
    return re.match(r'\D*(\d+)', deps['next']).group(1)


def flask_minor():
    m = re.search(r'^Flask==(\d+)\.(\d+)', (ROOT / 'backend' / 'requirements.txt').read_text(), re.M | re.I)
    return f'{m.group(1)}.{m.group(2)}'


def postgres_major():
    m = re.search(r'^FROM postgres:(\d+)', (ROOT / 'database' / 'Dockerfile').read_text(), re.M)
    return m.group(1)


def mcp_tool_count():
    pattern = re.compile(r'^\s*@(?:mcp|server)\.tool\b', re.M)
    return sum(len(pattern.findall(p.read_text())) for p in (ROOT / 'mcp-server' / 'sheetstorm_mcp').rglob('*.py'))


def badges():
    return {
        'release.svg': ('release', f'v{released_version()}', BRAND),
        'license.svg': ('license', license_name(), BRAND),
        'nextjs.svg': ('Next.js', next_major(), DARK),
        'flask.svg': ('Flask', flask_minor(), DARK),
        'postgresql.svg': ('PostgreSQL', postgres_major(), DARK),
        'mcp.svg': ('MCP', f'{mcp_tool_count()} tools', DARK),
    }


def main(argv):
    check = '--check' in argv
    stale = []
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (label, value, color) in badges().items():
        svg = badge_svg(label, value, color)
        path = OUT / name
        if check:
            if not path.exists() or path.read_text() != svg:
                stale.append(f'{name} ({label}: {value})')
        else:
            path.write_text(svg)
            print(f'badges: {name}  {label}: {value}')
    if stale:
        print('badges: stale, run python3 ci/badges.py and commit: ' + ', '.join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
