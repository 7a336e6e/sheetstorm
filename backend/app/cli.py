"""`flask sheetstorm ...` commands and the periodic jobs runner.

Features register periodic work with ``register_job(name, fn, every_seconds=N)``.
``flask sheetstorm run-jobs`` (run every ``JOBS_INTERVAL_SECONDS`` by the
compose ``jobs`` service, or by host cron) runs each job that is due:

* ``jobs:last:<name>`` (Redis) holds the unix time of the last successful run;
  a job is due when ``now - last >= every_seconds``;
* ``jobs:lock:<name>`` is taken with ``SET NX EX`` so concurrent runners never
  execute the same job twice; it is released (only by its owner) afterwards.

A failing job does not update ``jobs:last`` (it is retried on the next tick)
and makes the command exit non-zero. Redis is required (as it is for the API).
"""
import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable

import click
from flask import current_app
from flask.cli import AppGroup

sheetstorm_cli = AppGroup('sheetstorm', help='SheetStorm maintenance commands.')

_JOB_NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
_RELEASE_LOCK = ("if redis.call('get', KEYS[1]) == ARGV[1] then "
                 "return redis.call('del', KEYS[1]) else return 0 end")


@dataclass
class Job:
    name: str
    fn: Callable
    every_seconds: int
    lock_ttl: int


JOBS: dict = {}


def register_job(name, fn, *, every_seconds, lock_ttl=None):
    """Register a periodic job. ``fn()`` runs inside the app context.

    lock_ttl: seconds the run lock is held at most (default: every_seconds,
    clamped to 60..3600); keep it above the job's worst-case runtime.
    """
    if not _JOB_NAME.match(name or ''):
        raise ValueError(f'invalid job name {name!r}')
    if not isinstance(every_seconds, int) or every_seconds <= 0:
        raise ValueError('every_seconds must be a positive int')
    if lock_ttl is None:
        lock_ttl = min(max(every_seconds, 60), 3600)
    JOBS[name] = Job(name, fn, every_seconds, int(lock_ttl))
    return fn


def _redis():
    import app as app_pkg
    return app_pkg.redis_client


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_jobs(only=None, force=False, now=None) -> dict:
    """Run due jobs; returns ``{name: 'ok'|'not_due'|'locked'|'error'}``."""
    r = _redis()
    if r is None:
        raise RuntimeError('REDIS_URL is not configured; the jobs runner needs Redis for locks')
    names = list(only) if only else sorted(JOBS)
    unknown = [n for n in names if n not in JOBS]
    if unknown:
        raise click.BadParameter(f'unknown job(s): {", ".join(unknown)}', param_hint='--only')

    from app import db
    results = {}
    for name in names:
        job = JOBS[name]
        current = int(now if now is not None else time.time())
        last = _as_int(r.get(f'jobs:last:{name}'))
        if not force and last is not None and current - last < job.every_seconds:
            results[name] = 'not_due'
            continue
        lock_key, token = f'jobs:lock:{name}', secrets.token_hex(16)
        if not r.set(lock_key, token, nx=True, ex=job.lock_ttl):
            results[name] = 'locked'
            continue
        try:
            job.fn()
            r.set(f'jobs:last:{name}', current)
            results[name] = 'ok'
        except Exception:
            current_app.logger.exception('Job %s failed', name)
            results[name] = 'error'
            try:
                db.session.rollback()
            except Exception:
                pass
        finally:
            try:
                r.eval(_RELEASE_LOCK, 1, lock_key, token)
            except Exception:
                current_app.logger.warning('Could not release job lock %s', lock_key)
    return results


@sheetstorm_cli.command('run-jobs')
@click.option('--only', multiple=True, help='Run only this job (repeatable).')
@click.option('--force', is_flag=True, help='Ignore the schedule (still honours the lock).')
def run_jobs_command(only, force):
    """Run every registered periodic job that is due."""
    results = run_jobs(only=only, force=force)
    for name, status in results.items():
        click.echo(f'{name}: {status}')
    if not results:
        click.echo('no jobs registered')
    if any(s == 'error' for s in results.values()):
        raise SystemExit(1)


@sheetstorm_cli.command('list-jobs')
def list_jobs_command():
    """List registered periodic jobs and their last successful run."""
    r = _redis()
    for name in sorted(JOBS):
        last = _as_int(r.get(f'jobs:last:{name}')) if r is not None else None
        click.echo(f'{name}\tevery {JOBS[name].every_seconds}s\tlast={last if last is not None else "never"}')


def register_cli(app):
    """Attach the ``sheetstorm`` command group to the Flask CLI."""
    app.cli.add_command(sheetstorm_cli)


# ---------------------------------------------------------------------------
# Audit log maintenance (retention purge + hash-chain verification).
# Both run daily as jobs and are also available as commands.
# ---------------------------------------------------------------------------

AUDIT_JOB_INTERVAL = 24 * 3600


def _audit_orgs(org_slug=None):
    from app.models import Organization
    query = Organization.query.order_by(Organization.slug)
    if org_slug:
        query = query.filter(Organization.slug == org_slug)
    orgs = query.all()
    if org_slug and not orgs:
        raise click.BadParameter(f'unknown organization {org_slug!r}', param_hint='--org')
    return orgs


def purge_audit_logs(org_slug=None, dry_run=False, batch_size=None):
    """Apply each organization's audit retention. Returns per-org summaries;
    an org that fails gets ``{'status': 'error'}`` and the others still run."""
    from app import db
    from app.services.audit_service import purge_org
    results = []
    for org in _audit_orgs(org_slug):
        try:
            results.append(purge_org(org, dry_run=dry_run, batch_size=batch_size))
        except Exception:
            current_app.logger.exception('Audit purge failed for %s', org.slug)
            db.session.rollback()
            results.append({'organization': org.slug, 'status': 'error'})
    return results


def verify_audit_chains(org_slug=None):
    """Verify each organization's audit chain (and the global chain when no
    org is given). Returns the summaries."""
    from app.services.audit_service import verify_chain
    summaries = [verify_chain(org.id) for org in _audit_orgs(org_slug)]
    if not org_slug:
        summaries.append(verify_chain(None))
    return summaries


def _print_summary(summary):
    import json
    click.echo(json.dumps(summary, default=str, sort_keys=True))


@sheetstorm_cli.command('purge-audit-logs')
@click.option('--org', 'org_slug', default=None, help='Only this organization (slug).')
@click.option('--dry-run', is_flag=True, help='Report what would be deleted; delete nothing.')
@click.option('--batch-size', type=click.IntRange(1, 100000), default=None, help='Rows per transaction.')
def purge_audit_logs_command(org_slug, dry_run, batch_size):
    """Delete audit rows older than each organization's retention (legal holds win)."""
    results = purge_audit_logs(org_slug, dry_run=dry_run, batch_size=batch_size)
    for summary in results:
        _print_summary(summary)
    if any(r.get('status') == 'error' for r in results):
        raise SystemExit(1)


@sheetstorm_cli.command('verify-audit-chain')
@click.option('--org', 'org_slug', default=None, help='Only this organization (slug).')
def verify_audit_chain_command(org_slug):
    """Verify the audit hash chain; exits non-zero when any chain fails."""
    summaries = verify_audit_chains(org_slug)
    for summary in summaries:
        _print_summary({k: v for k, v in summary.items() if k != 'failures'} | {'failures': summary['failures'][:10]})
    if not all(s['ok'] for s in summaries):
        raise SystemExit(1)


def _purge_audit_logs_job():
    if any(r.get('status') == 'error' for r in purge_audit_logs()):
        raise RuntimeError('audit purge failed for at least one organization')


def _verify_audit_chain_job():
    failed = [s['chain_key'] for s in verify_audit_chains() if not s['ok']]
    if failed:
        raise RuntimeError(f'audit chain verification failed: {", ".join(failed)}')


register_job('purge-audit-logs', _purge_audit_logs_job, every_seconds=AUDIT_JOB_INTERVAL, lock_ttl=3600)
register_job('verify-audit-chain', _verify_audit_chain_job, every_seconds=AUDIT_JOB_INTERVAL, lock_ttl=3600)
