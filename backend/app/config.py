"""Flask Configuration"""
import os
from datetime import timedelta


def _env_bool(name, default):
    """Parse a boolean env var; return `default` when unset/empty."""
    val = os.getenv(name)
    if val is None or val.strip() == '':
        return default
    return val.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name):
    """Parse a comma-separated env var into a list of non-empty items."""
    return [v.strip() for v in os.getenv(name, '').split(',') if v.strip()]


class BaseConfig:
    """Base configuration."""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://sheetstorm:changeme@localhost:5432/sheetstorm')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
    # Library defaults only: sign-in tokens get their lifetimes from the org
    # security policy (session.access_token_minutes 5..60, default 60;
    # session.refresh_token_days 1..30, default 7; services/session_service.py).
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    # Accept tokens from the Authorization header (API clients, MCP, tests) AND
    # from httpOnly cookies (browser). httpOnly cookies keep the JWT out of
    # JS/localStorage (XSS-resistant); CSRF protection guards cookie requests.
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'
    # Secure cookies default on in production (see ProductionConfig); the
    # JWT_COOKIE_SECURE env var overrides either way (e.g. plain-HTTP LAN
    # deployments must set JWT_COOKIE_SECURE=false or browsers drop cookies).
    JWT_COOKIE_SECURE = _env_bool('JWT_COOKIE_SECURE', False)
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_ACCESS_COOKIE_PATH = '/'
    # The httpOnly refresh cookie is only ever sent to the auth endpoints
    # (/auth/refresh, /auth/logout). Its CSRF double-submit cookie stays at
    # '/' so the SPA can read csrf_refresh_token and echo it in X-CSRF-TOKEN.
    JWT_REFRESH_COOKIE_PATH = '/api/v1/auth'
    JWT_ACCESS_CSRF_COOKIE_PATH = '/'
    JWT_REFRESH_CSRF_COOKIE_PATH = '/'
    # Seconds a just-rotated refresh token is still accepted (once) so that
    # concurrent refreshes from several tabs/clients don't log the user out.
    JWT_REFRESH_GRACE_SECONDS = int(os.getenv('JWT_REFRESH_GRACE_SECONDS', '30'))

    # CORS / Socket.IO: explicit allowlist (comma list) plus FRONTEND_URL.
    CORS_ORIGINS = _env_list('CORS_ORIGINS')

    # Chain-of-custody HMAC key. Falls back to SECRET_KEY (with a startup
    # warning) when unset — set a dedicated key so rotating SECRET_KEY does
    # not invalidate every custody signature.
    CUSTODY_SIGNING_KEY = os.getenv('CUSTODY_SIGNING_KEY', '')

    # Audit log governance (services/ledger.py, services/audit_service.py).
    # AUDIT_CHAIN_KEY keys the audit hash chain (HMAC). It falls back to
    # SECRET_KEY with a warning when unset; set a dedicated key and keep it
    # outside the database. AUDIT_CHAIN_PREVIOUS_KEYS (comma list) keeps rows
    # written under rotated keys verifiable.
    AUDIT_CHAIN_KEY = os.getenv('AUDIT_CHAIN_KEY', '')
    AUDIT_CHAIN_PREVIOUS_KEYS = _env_list('AUDIT_CHAIN_PREVIOUS_KEYS')
    AUDIT_EXPORT_MAX_ROWS = int(os.getenv('AUDIT_EXPORT_MAX_ROWS', '100000'))
    AUDIT_RETENTION_MIN_DAYS = 365
    AUDIT_PURGE_BATCH_SIZE = int(os.getenv('AUDIT_PURGE_BATCH_SIZE', '10000'))

    # Build metadata shown in the admin system status (platform admins only).
    APP_VERSION = os.getenv('APP_VERSION', '')
    GIT_COMMIT = os.getenv('GIT_COMMIT', '')

    # Local artifact storage directory (used when S3 is not configured).
    LOCAL_ARTIFACT_DIR = os.getenv('LOCAL_ARTIFACT_DIR', '/app/artifacts')

    # Hosts / CIDRs that admin-configured self-hosted integrations (MISP,
    # Velociraptor, TheHive, Cortex, Elastic, Splunk, S3/MinIO, Ollama,
    # openai_compatible) may target even when they resolve to private
    # addresses. Example: "ollama,misp.corp.local,10.20.0.0/16". Link-local /
    # cloud-metadata addresses are always blocked regardless.
    OUTBOUND_URL_ALLOWLIST = _env_list('OUTBOUND_URL_ALLOWLIST')

    # Global default for automatic IOC enrichment on creation (off by default;
    # the organization setting `auto_enrich_iocs` overrides it).
    IOC_AUTO_ENRICH = _env_bool('IOC_AUTO_ENRICH', False)

    # API keys (services/api_key_service.py). Secrets are stored only as
    # HMAC-SHA256(API_KEY_PEPPER, secret). Without a pepper one is derived
    # from SECRET_KEY (startup warning); set a dedicated random value
    # (`openssl rand -hex 32`) so rotating SECRET_KEY keeps keys valid.
    API_KEY_PEPPER = os.getenv('API_KEY_PEPPER', '')
    # Lifetime of the access token minted by POST /auth/token (1..60 minutes).
    API_KEY_TOKEN_TTL_MINUTES = int(os.getenv('API_KEY_TOKEN_TTL_MINUTES', '15'))
    # Caps on active (not revoked, not expired) keys.
    API_KEY_MAX_PER_USER = int(os.getenv('API_KEY_MAX_PER_USER', '10'))
    API_KEY_MAX_PER_SERVICE_ACCOUNT = int(os.getenv('API_KEY_MAX_PER_SERVICE_ACCOUNT', '25'))
    API_KEY_MAX_PER_ORG = int(os.getenv('API_KEY_MAX_PER_ORG', '200'))

    # Slug of the platform organization. Only holders of `system:manage` in
    # this org are platform admins (instance-wide settings and status).
    PLATFORM_ORG_SLUG = os.getenv('PLATFORM_ORG_SLUG', 'default')

    # Socket.IO runtime
    SOCKETIO_ASYNC_MODE = 'eventlet'

    # Encryption
    FERNET_KEY = os.getenv('FERNET_KEY', '')

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

    # S3 Storage
    S3_ENDPOINT = os.getenv('S3_ENDPOINT', '')
    S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY', '')
    S3_SECRET_KEY = os.getenv('S3_SECRET_KEY', '')
    S3_BUCKET = os.getenv('S3_BUCKET', 'sheetstorm-artifacts')
    S3_REGION = os.getenv('S3_REGION', 'us-east-1')

    # AI Providers
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    GOOGLE_AI_API_KEY = os.getenv('GOOGLE_AI_API_KEY', '')
    # Local / self-hosted LLMs (Ollama, vLLM, LM Studio, llama.cpp, LocalAI)
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', '')
    # Env fallback for the 'openai_compatible' provider (vLLM, LM Studio,
    # llama.cpp, LocalAI, Ollama /v1). It is NOT used by the 'openai' type and
    # is only paired with OPENAI_COMPATIBLE_API_KEY — the real OPENAI_API_KEY
    # is never sent to this (arbitrary) URL.
    OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', '')
    OPENAI_COMPATIBLE_API_KEY = os.getenv('OPENAI_COMPATIBLE_API_KEY', '')
    LOCAL_LLM_MODEL = os.getenv('LOCAL_LLM_MODEL', '')
    LOCAL_LLM_TIMEOUT = int(os.getenv('LOCAL_LLM_TIMEOUT', '120'))

    # Google Drive OAuth
    GOOGLE_DRIVE_CLIENT_ID = os.getenv('GOOGLE_DRIVE_CLIENT_ID', '')
    GOOGLE_DRIVE_CLIENT_SECRET = os.getenv('GOOGLE_DRIVE_CLIENT_SECRET', '')
    GOOGLE_DRIVE_REDIRECT_URI = os.getenv('GOOGLE_DRIVE_REDIRECT_URI', 'http://127.0.0.1:5000/api/v1/google-drive/oauth/callback')

    # GitHub OAuth
    GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID', '')
    GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET', '')
    GITHUB_OAUTH_REDIRECT_URI = os.getenv('GITHUB_OAUTH_REDIRECT_URI', 'http://127.0.0.1:3000/login/github/callback')

    # Slack
    SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')

    # Frontend URL (for OAuth redirects etc.)
    FRONTEND_URL = os.getenv('FRONTEND_URL', '')

    # File uploads
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max upload

    # Bcrypt
    BCRYPT_LOG_ROUNDS = 12


class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(BaseConfig):
    """Production configuration."""
    DEBUG = False

    # Stricter security in production (JWT_COOKIE_SECURE env still overrides)
    JWT_COOKIE_SECURE = _env_bool('JWT_COOKIE_SECURE', True)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SAMESITE = 'Strict'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    SESSION_COOKIE_HTTPONLY = True


class TestingConfig(BaseConfig):
    """Testing configuration (pytest). Uses fixed, test-only secrets so the
    suite never needs real ones; never use this config for a deployment."""
    TESTING = True
    SECRET_KEY = 'test-only-secret-key-not-for-production'
    JWT_SECRET_KEY = 'test-only-jwt-secret-key-not-for-production'
    CUSTODY_SIGNING_KEY = 'test-only-custody-signing-key'
    AUDIT_CHAIN_KEY = 'test-only-audit-chain-key'
    API_KEY_PEPPER = 'test-only-api-key-pepper'
    # Valid Fernet key (urlsafe base64 of 32 bytes), test-only.
    FERNET_KEY = 'dGVzdC1vbmx5LWZlcm5ldC1rZXktMzJieXRlcyEhISE='
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'TEST_DATABASE_URL',
        'postgresql://sheetstorm:changeme@localhost:5432/sheetstorm_test',
    )
    REDIS_URL = os.getenv('TEST_REDIS_URL', 'redis://localhost:6379/15')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    JWT_COOKIE_SECURE = False
    BCRYPT_LOG_ROUNDS = 4
    SOCKETIO_ASYNC_MODE = 'threading'
    RATELIMIT_ENABLED = False
