"""AI / user text in PDF reports is HTML-escaped before the Markdown
transforms, so it cannot inject markup into the WeasyPrint input."""
import pytest

from app.api.v1.endpoints.reports import _inline_md, _simple_markdown_to_html


@pytest.mark.parametrize('payload', [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(1)>',
    '<link rel="stylesheet" href="file:///etc/passwd">',
])
def test_markdown_html_is_escaped(payload):
    md = '\n'.join([
        f'# Title {payload}',
        f'Paragraph **bold {payload}** and `{payload}`',
        f'- item {payload}',
        f'1. step {payload}',
        f'| col {payload} | b |',
        '|---|---|',
        f'| {payload} | *x* |',
        '```',
        payload,
        '```',
    ])
    out = _simple_markdown_to_html(md)
    assert '<script' not in out and '<img' not in out and '<link' not in out
    assert '&lt;' in out


def test_markdown_formatting_still_rendered():
    out = _simple_markdown_to_html('## Findings\n\nThe **host** ran `cmd.exe` & *more*')
    assert '<h2>Findings</h2>' in out
    assert '<strong>host</strong>' in out and '<code>cmd.exe</code>' in out
    assert '<em>more</em>' in out and '&amp;' in out


def test_links_only_for_safe_schemes_and_attribute_cannot_break_out():
    assert _inline_md('[docs](https://example.com/a?b=1&c=2)') == \
        '<a href="https://example.com/a?b=1&amp;c=2">docs</a>'
    assert _inline_md('[x](javascript:alert(1))').startswith('x')
    assert '<a' not in _inline_md('[x](javascript:alert(1))')
    out = _inline_md('[x](https://e.com/" onmouseover="alert(1))')
    assert '" onmouseover' not in out


def test_code_fence_language_is_sanitised():
    out = _simple_markdown_to_html('```py"><script>\nx\n```')
    assert '<script' not in out and 'class="language-pyscript"' in out
