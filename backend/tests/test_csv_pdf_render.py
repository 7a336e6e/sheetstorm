"""W0-FND: utils/csv_safe.py and services/pdf_render.py (no external fetches,
autoescaped templates)."""
import pytest


@pytest.mark.parametrize('value,expected', [
    (None, ''), ('', ''), ('plain', 'plain'), (42, '42'),
    ("=cmd|' /C calc'!A0", "'=cmd|' /C calc'!A0"), ('+1', "'+1"), ('-1', "'-1"), ('@SUM(A1)', "'@SUM(A1)"),
    ('\tx', "'\tx"), ('\rx', "'\rx"), ('\nx', "'\nx"), ('a=b', 'a=b'),
])
def test_csv_safe(value, expected):
    from app.utils.csv_safe import csv_safe
    assert csv_safe(value) == expected


def test_artifacts_keeps_alias():
    from app.api.v1.endpoints import artifacts
    from app.utils.csv_safe import csv_safe
    assert artifacts._csv_safe is csv_safe


def test_html_to_pdf_refuses_external_urls(app, monkeypatch):
    from app.services import pdf_render
    seen = []

    def recorder(url, *a, **k):
        seen.append(url)
        raise ValueError('denied')
    monkeypatch.setattr(pdf_render, 'deny_all_url_fetcher', recorder)
    html = ('<html><head><link rel="stylesheet" href="http://169.254.169.254/x.css"></head>'
            '<body><img src="file:///etc/passwd"><img src="https://example.com/a.png">ok</body></html>')
    pdf = pdf_render.html_to_pdf(html)
    assert pdf.startswith(b'%PDF')
    assert any('169.254.169.254' in u for u in seen)
    assert any(u.startswith('file:') for u in seen)


def test_default_fetcher_raises():
    from app.services.pdf_render import deny_all_url_fetcher
    with pytest.raises(ValueError):
        deny_all_url_fetcher('http://example.com')


def test_render_pdf_autoescapes(app, monkeypatch):
    from jinja2 import ChoiceLoader, DictLoader
    from app.services import pdf_render
    captured = {}
    monkeypatch.setattr(pdf_render, 'html_to_pdf', lambda html: captured.setdefault('html', html) and b'%PDF')
    original = app.jinja_loader
    app.jinja_env.loader = ChoiceLoader([DictLoader({'fndtest/t.html': '<p>{{ v }}</p>'}), original])
    try:
        with app.test_request_context('/'):
            pdf_render.render_pdf('fndtest/t.html', v='<img src=x onerror=alert(1)>')
    finally:
        app.jinja_env.loader = original
    assert '&lt;img' in captured['html'] and '<img' not in captured['html']
