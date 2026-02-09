"""Auto-enrichment service for IOCs.

Automatically enriches IOC values (IPs, domains, hashes, emails) when
the corresponding integration is configured.  Designed to be called
after IOC creation — failures are silent (soft fallback) so missing
API keys never cause crashes.
"""
import logging
from typing import Optional
from app import db
from app.models import Integration
from app.services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Enriches IOC values against configured threat-intel integrations."""

    @staticmethod
    def _get_api_key(organization_id: str, integration_type: str) -> Optional[str]:
        """Safely retrieve an API key for the given integration type.
        Returns None if the integration is not configured / disabled / missing key.
        """
        try:
            integration = Integration.query.filter_by(
                organization_id=organization_id,
                type=integration_type,
                is_enabled=True,
            ).first()
            if not integration or not integration.credentials_encrypted:
                return None
            creds = EncryptionService.decrypt_json(integration.credentials_encrypted)
            return creds.get('api_key')
        except Exception:
            return None

    @classmethod
    def enrich_ip(cls, ip: str, organization_id: str) -> dict:
        """Enrich an IP address.  Returns enrichment dict (may be empty)."""
        import requests as req
        enrichment: dict = {}

        # AbuseIPDB
        key = cls._get_api_key(organization_id, 'abuseipdb')
        if key:
            try:
                resp = req.get(
                    'https://api.abuseipdb.com/api/v2/check',
                    params={'ipAddress': ip, 'maxAgeInDays': 90},
                    headers={'Key': key, 'Accept': 'application/json'},
                    timeout=8,
                )
                if resp.status_code == 200:
                    d = resp.json().get('data', {})
                    enrichment['abuseipdb'] = {
                        'abuse_confidence': d.get('abuseConfidenceScore'),
                        'total_reports': d.get('totalReports'),
                        'country': d.get('countryCode'),
                        'isp': d.get('isp'),
                        'is_tor': d.get('isTor'),
                    }
            except Exception as e:
                logger.debug(f'AbuseIPDB enrichment failed for {ip}: {e}')

        # VirusTotal
        key = cls._get_api_key(organization_id, 'virustotal')
        if key:
            try:
                resp = req.get(
                    f'https://www.virustotal.com/api/v3/ip_addresses/{ip}',
                    headers={'x-apikey': key},
                    timeout=8,
                )
                if resp.status_code == 200:
                    attrs = resp.json().get('data', {}).get('attributes', {})
                    stats = attrs.get('last_analysis_stats', {})
                    enrichment['virustotal'] = {
                        'malicious': stats.get('malicious', 0),
                        'suspicious': stats.get('suspicious', 0),
                        'reputation': attrs.get('reputation', 0),
                        'as_owner': attrs.get('as_owner'),
                        'country': attrs.get('country'),
                    }
            except Exception as e:
                logger.debug(f'VT enrichment failed for {ip}: {e}')

        return enrichment

    @classmethod
    def enrich_domain(cls, domain: str, organization_id: str) -> dict:
        """Enrich a domain.  Returns enrichment dict."""
        import requests as req
        enrichment: dict = {}

        key = cls._get_api_key(organization_id, 'virustotal')
        if key:
            try:
                resp = req.get(
                    f'https://www.virustotal.com/api/v3/domains/{domain}',
                    headers={'x-apikey': key},
                    timeout=8,
                )
                if resp.status_code == 200:
                    attrs = resp.json().get('data', {}).get('attributes', {})
                    stats = attrs.get('last_analysis_stats', {})
                    enrichment['virustotal'] = {
                        'malicious': stats.get('malicious', 0),
                        'suspicious': stats.get('suspicious', 0),
                        'reputation': attrs.get('reputation', 0),
                        'registrar': attrs.get('registrar'),
                    }
            except Exception as e:
                logger.debug(f'VT domain enrichment failed for {domain}: {e}')

        return enrichment

    @classmethod
    def enrich_hash(cls, file_hash: str, organization_id: str) -> dict:
        """Enrich a file hash.  Returns enrichment dict."""
        import requests as req
        enrichment: dict = {}

        key = cls._get_api_key(organization_id, 'virustotal')
        if key:
            try:
                resp = req.get(
                    f'https://www.virustotal.com/api/v3/files/{file_hash}',
                    headers={'x-apikey': key},
                    timeout=8,
                )
                if resp.status_code == 200:
                    attrs = resp.json().get('data', {}).get('attributes', {})
                    stats = attrs.get('last_analysis_stats', {})
                    enrichment['virustotal'] = {
                        'malicious': stats.get('malicious', 0),
                        'suspicious': stats.get('suspicious', 0),
                        'harmless': stats.get('harmless', 0),
                        'detection_ratio': f"{stats.get('malicious', 0)}/{sum(stats.values())}",
                        'file_type': attrs.get('type_description'),
                        'file_name': attrs.get('meaningful_name'),
                        'tags': attrs.get('tags', [])[:10],
                    }
            except Exception as e:
                logger.debug(f'VT hash enrichment failed for {file_hash}: {e}')

        return enrichment

    @classmethod
    def auto_enrich_ioc(cls, ioc_type: str, value: str, organization_id: str) -> dict:
        """Auto-enrich an IOC based on its type.  Returns enrichment
        metadata dict suitable for storing in extra_data.

        Never raises — all failures are silently swallowed so the
        caller's primary operation is never disrupted.
        """
        try:
            if ioc_type in ('ip-src', 'ip-dst', 'ip'):
                return cls.enrich_ip(value, organization_id)
            elif ioc_type in ('domain', 'hostname'):
                return cls.enrich_domain(value, organization_id)
            elif ioc_type in ('md5', 'sha1', 'sha256', 'hash'):
                return cls.enrich_hash(value, organization_id)
            return {}
        except Exception as e:
            logger.warning(f'Auto-enrichment failed for {ioc_type}={value}: {e}')
            return {}
