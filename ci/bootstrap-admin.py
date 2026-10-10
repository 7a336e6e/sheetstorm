#!/usr/bin/env python3
"""Finish the bootstrap admin of a fresh CI / test stack: wait for the API,
then do the mandatory first-sign-in password change.

    python3 ci/bootstrap-admin.py [--base URL] [--env-file .env]

Reads ADMIN_EMAIL / ADMIN_PASSWORD from the environment (or the env file),
signs in, changes the password to a new random one and writes it back as
ADMIN_PASSWORD to the env file and, under GitHub Actions, to GITHUB_ENV
(masked). Idempotent: an admin that no longer needs a change is left alone.
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request


def call(base, method, path, body=None, token=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except ValueError:
            return e.code, {}


def read_env(path):
    out = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                if '=' in line and not line.lstrip().startswith('#'):
                    k, v = line.rstrip('\n').split('=', 1)
                    out[k.strip()] = v
    return out


def write_env_value(path, key, value):
    with open(path) as f:
        lines = f.readlines()
    with open(path, 'w') as f:
        for line in lines:
            f.write(f'{key}={value}\n' if line.startswith(key + '=') else line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('E2E_BASE_URL', 'http://localhost:8080'))
    ap.add_argument('--env-file', default='.env')
    ap.add_argument('--timeout', type=int, default=300)
    args = ap.parse_args()
    api = args.base.rstrip('/') + '/api/v1'
    env = read_env(args.env_file)
    email = os.environ.get('ADMIN_EMAIL') or env.get('ADMIN_EMAIL')
    password = os.environ.get('ADMIN_PASSWORD') or env.get('ADMIN_PASSWORD')
    if not email or not password:
        sys.exit('bootstrap-admin: ADMIN_EMAIL / ADMIN_PASSWORD are required')

    deadline = time.time() + args.timeout
    while True:
        try:
            status, _ = call(api, 'GET', '/health')
            if status == 200:
                break
        except OSError:
            pass
        if time.time() > deadline:
            sys.exit(f'bootstrap-admin: {api}/health not ready after {args.timeout}s')
        time.sleep(3)

    status, data = call(api, 'POST', '/auth/login', {'email': email, 'password': password})
    if status != 200:
        sys.exit(f'bootstrap-admin: login failed ({status}): {data.get("message")}')
    if not data.get('user', {}).get('must_change_password'):
        print('bootstrap-admin: admin already active; nothing to do')
        return

    new_password = secrets.token_urlsafe(18) + 'aA1!'
    status, data = call(api, 'POST', '/auth/change-password',
                        {'current_password': password, 'new_password': new_password},
                        token=data['access_token'])
    if status != 200:
        sys.exit(f'bootstrap-admin: password change failed ({status}): {data.get("message")}')

    if os.path.exists(args.env_file):
        write_env_value(args.env_file, 'ADMIN_PASSWORD', new_password)
    github_env = os.environ.get('GITHUB_ENV')
    if github_env:
        print(f'::add-mask::{new_password}')
        with open(github_env, 'a') as f:
            f.write(f'ADMIN_PASSWORD={new_password}\n')
    print(f'bootstrap-admin: {email} is ready')


if __name__ == '__main__':
    main()
