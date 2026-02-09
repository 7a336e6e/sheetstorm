"""Integration configuration resolver.

Resolves configuration values by checking database-stored integrations first,
then falling back to environment variables / Flask config.
"""
import json
import os
from typing import Optional, Dict, Any


class IntegrationConfigResolver:
    """Resolves config values from DB integrations with .env fallback."""

    _cache: Dict[str, Any] = {}
    _cache_ttl = 60  # seconds
    _cache_timestamps: Dict[str, float] = {}

    @staticmethod
    def get_credentials(integration_type: str, org_id: str = None) -> Optional[Dict[str, Any]]:
        """Get decrypted credentials for an integration type.

        Checks database first, falls back to environment config.

        Args:
            integration_type: e.g. 'openai', 'slack', 's3', 'oauth_github'
            org_id: Organization ID (optional, uses first enabled if not set)

        Returns:
            Dict of credentials or None
        """
        from flask import current_app
        try:
            return IntegrationConfigResolver._resolve_from_db(integration_type, org_id)
        except Exception:
            pass

        # Fallback to .env / Flask config
        return IntegrationConfigResolver._resolve_from_env(integration_type, current_app)

    @staticmethod
    def get_config(integration_type: str, org_id: str = None) -> Optional[Dict[str, Any]]:
        """Get non-secret config for an integration type."""
        try:
            from app.models.integration import Integration
            query = Integration.query.filter_by(type=integration_type, is_enabled=True)
            if org_id:
                query = query.filter_by(organization_id=org_id)
            integration = query.first()
            if integration:
                return integration.config or {}
        except Exception:
            pass
        return {}

    @staticmethod
    def is_configured(integration_type: str, org_id: str = None) -> bool:
        """Check if an integration type is configured (DB or env)."""
        creds = IntegrationConfigResolver.get_credentials(integration_type, org_id)
        return creds is not None and len(creds) > 0

    @staticmethod
    def _resolve_from_db(integration_type: str, org_id: str = None) -> Optional[Dict[str, Any]]:
        """Resolve credentials from database."""
        from app.models.integration import Integration
        from app.services.encryption_service import encryption_service

        query = Integration.query.filter_by(type=integration_type, is_enabled=True)
        if org_id:
            query = query.filter_by(organization_id=org_id)
        integration = query.first()

        if not integration or not integration.credentials_encrypted:
            return None

        decrypted = encryption_service.decrypt(integration.credentials_encrypted)
        if not decrypted:
            return None

        creds = json.loads(decrypted)

        # Merge config (non-secret) with credentials
        result = {}
        if integration.config:
            result.update(integration.config)
        result.update(creds)

        return result if result else None

    @staticmethod
    def _resolve_from_env(integration_type: str, app) -> Optional[Dict[str, Any]]:
        """Resolve credentials from environment / Flask config."""
        env_map = {
            'openai': lambda: _non_empty({'api_key': app.config.get('OPENAI_API_KEY')}),
            'google_ai': lambda: _non_empty({'api_key': app.config.get('GOOGLE_AI_API_KEY')}),
            'slack': lambda: _non_empty({'webhook_url': app.config.get('SLACK_WEBHOOK_URL')}),
            's3': lambda: _non_empty({
                'access_key': app.config.get('S3_ACCESS_KEY'),
                'secret_key': app.config.get('S3_SECRET_KEY'),
                'endpoint': app.config.get('S3_ENDPOINT'),
                'bucket': app.config.get('S3_BUCKET'),
                'region': app.config.get('S3_REGION'),
            }),
            'oauth_github': lambda: _non_empty({
                'client_id': app.config.get('GITHUB_CLIENT_ID'),
                'client_secret': app.config.get('GITHUB_CLIENT_SECRET'),
            }),
            'oauth_google': lambda: _non_empty({
                'client_id': app.config.get('GOOGLE_DRIVE_CLIENT_ID'),
                'client_secret': app.config.get('GOOGLE_DRIVE_CLIENT_SECRET'),
            }),
        }

        resolver = env_map.get(integration_type)
        if resolver:
            return resolver()
        return None


def _non_empty(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return dict only if at least one value is non-empty."""
    filtered = {k: v for k, v in d.items() if v}
    return filtered if filtered else None


# Singleton instance
config_resolver = IntegrationConfigResolver()
