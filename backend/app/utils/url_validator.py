"""Utilities for validating outbound HTTP(S) URLs (SSRF protection).

Two tiers:

* default — only publicly routable destinations are allowed;
* ``allow_allowlisted_private=True`` (admin-configured self-hosted
  integrations: MISP, Velociraptor, TheHive, Cortex, Elastic, Splunk,
  S3/MinIO, Ollama, openai_compatible) — private / loopback targets are
  additionally allowed when the URL's host matches ``OUTBOUND_URL_ALLOWLIST``
  (hostnames, ``.suffix`` domains or CIDRs). E.g. the bundled Ollama service is
  reachable once the allowlist contains ``ollama``.

Link-local and cloud-metadata destinations (169.254.0.0/16, fe80::/10,
fd00:ec2::254, metadata.google.internal, ...) are ALWAYS blocked, whatever the
allowlist says. Note: validation resolves DNS at check time; a host that
re-resolves differently afterwards (DNS rebinding) is a residual risk.
"""
import ipaddress
import socket
from urllib.parse import urlparse


# Never reachable, even when allowlisted.
_ALWAYS_BLOCKED_NETWORKS = (
    ipaddress.ip_network('169.254.0.0/16'),     # IPv4 link-local / cloud metadata
    ipaddress.ip_network('fe80::/10'),          # IPv6 link-local
    ipaddress.ip_network('fd00:ec2::254/128'),  # AWS IMDS over IPv6
    ipaddress.ip_network('0.0.0.0/8'),          # "this network"
    ipaddress.ip_network('::/128'),             # unspecified
)
_ALWAYS_BLOCKED_HOSTNAMES = {
    'metadata.google.internal', 'metadata.goog', 'metadata',
    'instance-data', 'instance-data.ec2.internal',
}

_NAT64_PREFIX = ipaddress.ip_network('64:ff9b::/96')


def _embedded_ipv4(ip):
    """IPv4 addresses embedded in an IPv6 address (mapped / 6to4 / NAT64 / Teredo)."""
    if ip.version != 6:
        return []
    out = []
    if ip.ipv4_mapped:
        out.append(ip.ipv4_mapped)
    if ip.sixtofour:
        out.append(ip.sixtofour)
    if ip.teredo:
        out.extend(ip.teredo)
    if ip in _NAT64_PREFIX:
        out.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return out


def _candidates(ip):
    return [ip, *_embedded_ipv4(ip)]


def _is_always_blocked(ip) -> bool:
    for addr in _candidates(ip):
        if addr.is_link_local or addr.is_unspecified or addr.is_multicast:
            return True
        if any(addr.version == n.version and addr in n for n in _ALWAYS_BLOCKED_NETWORKS):
            return True
    return False


def _is_non_public(ip) -> bool:
    """Private, loopback, reserved, CGNAT, documentation, ... (not globally routable)."""
    for addr in _candidates(ip):
        if (addr.is_private or addr.is_loopback or addr.is_reserved
                or addr.is_link_local or addr.is_unspecified or addr.is_multicast
                or not addr.is_global):
            return True
    return False


# Backwards-compatible name used by older callers/tests.
def _is_blocked_ip(ip_address) -> bool:
    return _is_always_blocked(ip_address) or _is_non_public(ip_address)


def _load_allowlist(allowlist):
    if allowlist is not None:
        return list(allowlist)
    try:
        from flask import current_app
        return list(current_app.config.get('OUTBOUND_URL_ALLOWLIST') or [])
    except RuntimeError:  # no app context
        return []


def _host_allowlisted(hostname: str, ips, allowlist) -> bool:
    host = hostname.lower().rstrip('.')
    for entry in allowlist:
        entry = entry.strip().lower()
        if not entry:
            continue
        try:
            net = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            net = None
        if net is not None:
            # Every resolved address must fall inside an allowlisted network.
            if ips and all(ip.version == net.version and ip in net for ip in ips):
                return True
            continue
        if entry.startswith('.'):
            if host.endswith(entry) or host == entry[1:]:
                return True
        elif host == entry.rstrip('.'):
            return True
    return False


def validate_outbound_url(url: str, allow_allowlisted_private: bool = False,
                          allowlist=None) -> tuple[bool, str]:
    """Return (ok, reason) for whether an outbound URL is safe to call.

    allow_allowlisted_private: permit private/loopback destinations when the
        host is on OUTBOUND_URL_ALLOWLIST (self-hosted integrations only).
    allowlist: override the configured allowlist (tests).
    """
    if not url or not isinstance(url, str):
        return False, 'URL is required'
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False, 'Invalid URL'

    if parsed.scheme not in ('http', 'https'):
        return False, 'URL scheme must be http or https'

    try:
        hostname = parsed.hostname
        parsed.port  # noqa: B018 — raises ValueError on an invalid port
    except ValueError:
        return False, 'Invalid hostname or port'

    if not hostname:
        return False, 'URL hostname is required'

    if hostname.lower().rstrip('.') in _ALWAYS_BLOCKED_HOSTNAMES:
        return False, 'URL targets a cloud metadata service'

    try:
        resolved_addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError) as exc:
        return False, f'DNS resolution failed for hostname: {exc}'

    if not resolved_addresses:
        return False, 'Hostname did not resolve to any IP address'

    ips = []
    for result in resolved_addresses:
        address = result[4][0].split('%', 1)[0]  # strip IPv6 zone id
        try:
            ips.append(ipaddress.ip_address(address))
        except ValueError:
            return False, f'Resolved address is not a valid IP address: {address}'

    for ip in ips:
        if _is_always_blocked(ip):
            return False, f'URL resolves to blocked IP address {ip}'

    if any(_is_non_public(ip) for ip in ips):
        if allow_allowlisted_private and _host_allowlisted(hostname, ips, _load_allowlist(allowlist)):
            return True, ''
        blocked = next(ip for ip in ips if _is_non_public(ip))
        hint = ' (add the host to OUTBOUND_URL_ALLOWLIST to allow a self-hosted service)' \
            if allow_allowlisted_private else ''
        return False, f'URL resolves to non-public IP address {blocked}{hint}'

    return True, ''
