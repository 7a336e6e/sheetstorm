"""W0-FND: app/cli.py — `flask sheetstorm run-jobs` registry, schedule and lock."""
import uuid

import pytest


@pytest.fixture
def job(app, redis_client):
    from app import cli
    names = []

    def make(fn, every_seconds=3600):
        name = f'fndtest-{uuid.uuid4().hex[:8]}'
        cli.register_job(name, fn, every_seconds=every_seconds)
        names.append(name)
        return name
    yield make
    for n in names:
        cli.JOBS.pop(n, None)
        redis_client.delete(f'jobs:last:{n}', f'jobs:lock:{n}')


def _run(app, *args):
    return app.test_cli_runner().invoke(args=['sheetstorm', 'run-jobs', *args])


def test_run_jobs_runs_once_per_interval(app, job, redis_client):
    calls = []
    name = job(lambda: calls.append(1))
    res = _run(app, '--only', name)
    assert res.exit_code == 0, res.output
    assert f'{name}: ok' in res.output and calls == [1]
    assert redis_client.get(f'jobs:last:{name}') is not None
    res = _run(app, '--only', name)
    assert f'{name}: not_due' in res.output and calls == [1]
    res = _run(app, '--only', name, '--force')
    assert f'{name}: ok' in res.output and calls == [1, 1]
    assert redis_client.get(f'jobs:lock:{name}') is None  # released


def test_lock_prevents_concurrent_run(app, job, redis_client):
    calls = []
    name = job(lambda: calls.append(1))
    redis_client.set(f'jobs:lock:{name}', 'someone-else', ex=60)
    res = _run(app, '--only', name)
    assert f'{name}: locked' in res.output and calls == []
    assert redis_client.get(f'jobs:lock:{name}') == b'someone-else'  # not stolen


def test_failing_job_exits_nonzero_and_is_retried(app, job, redis_client):
    def boom():
        raise RuntimeError('fail')
    name = job(boom)
    res = _run(app, '--only', name)
    assert res.exit_code == 1 and f'{name}: error' in res.output
    assert redis_client.get(f'jobs:last:{name}') is None
    assert redis_client.get(f'jobs:lock:{name}') is None


def test_unknown_job_and_registration_validation(app):
    from app import cli
    res = _run(app, '--only', 'does-not-exist')
    assert res.exit_code != 0
    with pytest.raises(ValueError):
        cli.register_job('Bad Name', lambda: None, every_seconds=60)
    with pytest.raises(ValueError):
        cli.register_job('ok-name', lambda: None, every_seconds=0)


def test_list_jobs(app, job):
    name = job(lambda: None, every_seconds=86400)
    res = app.test_cli_runner().invoke(args=['sheetstorm', 'list-jobs'])
    assert res.exit_code == 0 and name in res.output and 'every 86400s' in res.output
