# SheetStorm release bundle

Everything needed to run a released SheetStorm version from its published
container images. You don't need a source checkout or a build.

| File | Purpose |
|---|---|
| `docker-compose.yml` | The stack, on `ghcr.io/7a336e6e/sheetstorm-*` images pinned to this release |
| `.env.example` | Every setting, with defaults. `install.sh` turns it into `.env` |
| `install.sh` | First install and upgrades |
| `scripts/backup.sh`, `scripts/restore.sh` | Backups of the database and evidence files |

## Install

Requirements: Docker with Compose v2, and 2 GB RAM (4 GB recommended).

```bash
./install.sh
```

The installer:
1. creates `.env` with fresh random secrets;
2. pulls the images and starts the stack;
3. creates the first administrator.

Then open <http://localhost:8080> and sign in as `admin@sheetstorm.local`.
With `ADMIN_PASSWORD` empty, the installer prints a one-time password once,
and you choose a new one at first sign-in.

To serve other host names, put TLS in front of the proxy (a load balancer,
Caddy, a tunnel and so on). Then set `FRONTEND_URL` and `CORS_ORIGINS` in
`.env` to the `https://` origin and run `docker compose up -d`. Every setting
is documented in the
[configuration guide](https://github.com/7a336e6e/sheetstorm/blob/main/assets/docs/configuration.md).

## Verify what you run

The images carry GitHub build-provenance attestations. The bundle files are
listed in `SHA256SUMS` on the release page and attested too:

```bash
gh attestation verify oci://ghcr.io/7a336e6e/sheetstorm-backend:<version> --owner 7a336e6e
gh attestation verify sheetstorm-<version>.tar.gz --owner 7a336e6e
```

## Back up, upgrade and restore

```bash
scripts/backup.sh /srv/backups        # database + evidence, checksummed
```

Keep `.env` safe and separate from the backups. Without the same
`FERNET_KEY`, `CUSTODY_SIGNING_KEY` and `AUDIT_CHAIN_KEY`, a restore cannot
decrypt credentials or verify signatures.

To upgrade:
1. Read the release notes.
2. Back up.
3. Unpack the newer bundle over this directory. Your `.env` is kept.
4. Run `./install.sh`. Database migrations run automatically.

To restore: `scripts/restore.sh <backup-dir> --yes`.

More detail, including verifying images and restoring on another host, is in
the [operations guide](https://github.com/7a336e6e/sheetstorm/blob/main/assets/docs/operations.md).
