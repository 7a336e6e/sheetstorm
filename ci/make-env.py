#!/usr/bin/env python3
"""Write a throwaway .env for a CI / test stack: .env.example with fresh random
secrets and a random bootstrap admin password.

    python3 ci/make-env.py [OUT]          # default: .env (refuses to overwrite)

Overrides may be passed as KEY=VALUE arguments after OUT. When GITHUB_ENV is
set (GitHub Actions), ADMIN_EMAIL / ADMIN_PASSWORD are exported to later steps
and the password is masked in the log. Never use this for a real deployment:
start.sh keeps existing keys, this script does not.
"""
import base64
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    out = argv[1] if len(argv) > 1 and '=' not in argv[1] else '.env'
    extra = dict(a.split('=', 1) for a in argv[1:] if '=' in a)
    if os.path.exists(out):
        sys.exit(f'make-env: {out} exists; refusing to overwrite')

    pg_password = secrets.token_hex(16)
    values = {
        'POSTGRES_PASSWORD': pg_password,
        'DATABASE_URL': f'postgresql://sheetstorm:{pg_password}@database:5432/sheetstorm',
        'SECRET_KEY': secrets.token_hex(32),
        'JWT_SECRET_KEY': secrets.token_hex(32),
        'FERNET_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
        'CUSTODY_SIGNING_KEY': secrets.token_hex(32),
        'AUDIT_CHAIN_KEY': secrets.token_hex(32),
        'API_KEY_PEPPER': secrets.token_hex(32),
        'ADMIN_EMAIL': 'admin@ci.sheetstorm.test',
        # Meets the default policy: length, upper, lower, digit, symbol.
        'ADMIN_PASSWORD': secrets.token_urlsafe(18) + 'aA1!',
    }
    values.update(extra)

    lines, seen = [], set()
    with open(os.path.join(ROOT, '.env.example')) as f:
        for line in f:
            key = line.split('=', 1)[0].strip()
            if not line.lstrip().startswith('#') and '=' in line and key in values:
                lines.append(f'{key}={values[key]}\n')
                seen.add(key)
            else:
                lines.append(line)
    lines += [f'{k}={v}\n' for k, v in values.items() if k not in seen]

    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.writelines(lines)

    github_env = os.environ.get('GITHUB_ENV')
    if github_env:
        print(f"::add-mask::{values['ADMIN_PASSWORD']}")
        with open(github_env, 'a') as f:
            f.write(f"ADMIN_EMAIL={values['ADMIN_EMAIL']}\n")
            f.write(f"ADMIN_PASSWORD={values['ADMIN_PASSWORD']}\n")
    print(f'make-env: wrote {out}')


if __name__ == '__main__':
    main(sys.argv)
