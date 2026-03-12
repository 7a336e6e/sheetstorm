"""Expand audit_logs with richer request context fields.

Adds: request_query_params, request_body_summary, content_type, referrer,
origin, duration_ms, geo_country, geo_city, geo_region, cf_ray, browser,
os, device_type.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'expand_audit_fields'
down_revision = 'platform_refactor_v2'
branch_labels = None
depends_on = None


def upgrade():
    columns_to_add = [
        ('request_query_params', postgresql.JSONB(), None),
        ('request_body_summary', postgresql.JSONB(), None),
        ('content_type', sa.String(255), None),
        ('referrer', sa.Text(), None),
        ('origin', sa.String(255), None),
        ('duration_ms', sa.Float(), None),
        ('geo_country', sa.String(100), None),
        ('geo_city', sa.String(255), None),
        ('geo_region', sa.String(255), None),
        ('cf_ray', sa.String(100), None),
        ('browser', sa.String(100), None),
        ('os', sa.String(100), None),
        ('device_type', sa.String(50), None),
    ]
    for col_name, col_type, default in columns_to_add:
        op.add_column(
            'audit_logs',
            sa.Column(col_name, col_type, nullable=True, server_default=default),
        )


def downgrade():
    columns_to_drop = [
        'request_query_params', 'request_body_summary', 'content_type',
        'referrer', 'origin', 'duration_ms', 'geo_country', 'geo_city',
        'geo_region', 'cf_ray', 'browser', 'os', 'device_type',
    ]
    for col_name in columns_to_drop:
        op.drop_column('audit_logs', col_name)
