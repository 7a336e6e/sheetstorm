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
