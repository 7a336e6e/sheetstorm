"""Utilities for validating outbound HTTP(S) URLs."""
import ipaddress
import socket
from urllib.parse import urlparse


_BLOCKED_NETWORKS = (
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('::1/128'),
)


def _is_blocked_ip(ip_address: ipaddress._BaseAddress) -> bool:
    mapped = getattr(ip_address, 'ipv4_mapped', None)
    addresses = (ip_address, mapped) if mapped else (ip_address,)
    return any(
        address.version == network.version and address in network
        for address in addresses
        for network in _BLOCKED_NETWORKS
    )


def validate_outbound_url(url: str) -> tuple[bool, str]:
    """Return whether an outbound URL is safe to call."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, 'Invalid URL'

    if parsed.scheme not in ('http', 'https'):
        return False, 'URL scheme must be http or https'

    try:
        hostname = parsed.hostname
    except ValueError:
        return False, 'Invalid hostname'

    if not hostname:
        return False, 'URL hostname is required'

    try:
        resolved_addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f'DNS resolution failed for hostname: {exc}'
    except OSError as exc:
        return False, f'DNS resolution failed for hostname: {exc}'

    if not resolved_addresses:
        return False, 'Hostname did not resolve to any IP address'

    for result in resolved_addresses:
        address = result[4][0]
        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError:
            return False, f'Resolved address is not a valid IP address: {address}'

        if _is_blocked_ip(ip_address):
            return False, f'URL resolves to blocked IP address {address}'

    return True, ''
