"""Safe HTML -> PDF rendering (WeasyPrint) shared by every PDF the backend makes.

* WeasyPrint never fetches external resources: every URL (http, https, file,
  ftp, data) is refused, so attacker-influenced HTML (incident data, AI output)
  cannot trigger SSRF or local-file reads while rendering.
* ``render_pdf`` renders a Jinja template from ``app/templates/<feature>/``
  through Flask's ``render_template`` (autoescape on for ``.html``).
"""
from flask import render_template

_fetcher = None


def deny_all_url_fetcher(url, *args, **kwargs):
    """URL fetcher that refuses every URL (WeasyPrint logs and skips it)."""
    raise ValueError(f'External resource fetching is disabled ({str(url)[:80]})')


def _deny_all_fetcher():
    """A WeasyPrint URLFetcher instance whose fetch() is deny_all_url_fetcher.

    WeasyPrint >= 66 expects a URLFetcher instance (it reads private attributes
    such as ``_fail_on_errors``), not a bare function.
    """
    global _fetcher
    if _fetcher is None:
        from weasyprint.urls import URLFetcher

        class _DenyAllURLFetcher(URLFetcher):
            def fetch(self, url, headers=None):
                return deny_all_url_fetcher(url)

        _fetcher = _DenyAllURLFetcher(allowed_protocols=())
    return _fetcher


def html_to_pdf(html: str) -> bytes:
    """Render an HTML string to PDF bytes with external fetching disabled."""
    from weasyprint import HTML
    return HTML(string=html, base_url=None, url_fetcher=_deny_all_fetcher()).write_pdf()


def render_pdf(template: str, **ctx) -> bytes:
    """Render ``template`` (autoescaped Jinja) and convert it to PDF bytes."""
    return html_to_pdf(render_template(template, **ctx))
