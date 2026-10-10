# Operations

Running SheetStorm with Docker Compose: installing from source or from the
published images, upgrading, backing up and restoring.

## Install from a release or from source

**From a release** (recommended for running SheetStorm). Every release on
GitHub carries three assets:

| Asset | Contents |
|---|---|
| `sheetstorm-X.Y.Z.tar.gz` (and `sheetstorm.tar.gz`, the same file) | `docker-compose.yml`, `.env.example`, `install.sh`, `README.md`, `scripts/backup.sh` and `scripts/restore.sh` in a `sheetstorm/` directory |
| `docker-compose.yml` | The same compose file on its own |
| `SHA256SUMS` | Checksums of the above |

```bash
curl -fsSLO https://github.com/7a336e6e/sheetstorm/releases/download/v1.0.1/sheetstorm-1.0.1.tar.gz
tar -xzf sheetstorm-1.0.1.tar.gz && cd sheetstorm && ./install.sh
```

The compose file runs the release's images and is generated from the
repository's `docker-compose.yml`, so the stack is the same as a source
install. Its project name is fixed (`sheetstorm`), which keeps the same Docker
volumes wherever you unpack it. `-p` or `COMPOSE_PROJECT_NAME` gives a second
instance its own volumes.

`install.sh` does the following:
1. **First run:** creates `.env` with fresh random secrets: the database
   password, `SECRET_KEY`, `JWT_SECRET_KEY`, `FERNET_KEY`,
   `CUSTODY_SIGNING_KEY`, `AUDIT_CHAIN_KEY` and `API_KEY_PEPPER`.
2. **Later runs:** keeps the existing `.env` and fills in only empty core keys.
   On an existing install without `CUSTODY_SIGNING_KEY`, it sets that key to
   the current `SECRET_KEY`, so earlier custody signatures keep verifying.
3. **A database volume exists but `.env` is missing:** warns, and generates
   neither a database password nor an audit key.
4. Pulls the images and starts the stack (`up --wait`).
5. Creates the first administrator on a fresh database.

`./start.sh` uses the same `.env` logic.

**Images.** Every release publishes multi-arch (amd64 + arm64) images to the
GitHub Container Registry:

| Image | Service |
|---|---|
| `ghcr.io/7a336e6e/sheetstorm-backend` | `backend` and `jobs` |
| `ghcr.io/7a336e6e/sheetstorm-frontend` | `frontend` |
| `ghcr.io/7a336e6e/sheetstorm-proxy` | `proxy` |
| `ghcr.io/7a336e6e/sheetstorm-database` | `database` (PostgreSQL 16 with the init scripts) |
| `ghcr.io/7a336e6e/sheetstorm-mcp-server` | `mcp-server` |

Tags: `X.Y.Z` (immutable), `X.Y` (latest patch) and `latest` (latest stable
release). Pin an exact version in production.

`SHEETSTORM_VERSION` and `SHEETSTORM_REGISTRY` in `.env` override the bundle's
image tag and registry (for example a mirror).

**From source:** run `./start.sh`, or `docker compose up -d --build` once
`.env` exists. See the [README](../../README.md#quick-start).

`./start.sh --version X.Y.Z` runs the release images from a source checkout.
It sets `SHEETSTORM_VERSION` and
`COMPOSE_FILE=docker-compose.yml:docker-compose.images.yml` in `.env`.

The frontend image is built with `NEXT_PUBLIC_API_URL=/api/v1` (the bundled
proxy). Supabase sign-in needs build-time `NEXT_PUBLIC_SUPABASE_*` values, so
build the frontend from source if you use it.

### Verifying an image

Each image carries a GitHub build-provenance attestation (Sigstore-signed,
bound to the release workflow run) plus BuildKit SBOM and provenance. The
bundle files are attested too. Check them before you run or upgrade:

```bash
gh attestation verify oci://ghcr.io/7a336e6e/sheetstorm-backend:1.0.1 --owner 7a336e6e
gh attestation verify sheetstorm-1.0.1.tar.gz --owner 7a336e6e
sha256sum -c SHA256SUMS --ignore-missing
```

A successful check proves the image was built by this repository's
`release.yml` from the tagged commit. To pin images by digest, take the
`sha256:` value from that output or from the release notes.

## Upgrading

1. Read the release notes: [CHANGELOG.md](../../CHANGELOG.md) lists behavior
   changes and upgrade notes per version.
2. Back up (below).
3. Upgrade the way you installed:
   - **Release bundle:** unpack the new bundle over the same directory (your
     `.env` is kept) and run `./install.sh`. The newest one is always
     `https://github.com/7a336e6e/sheetstorm/releases/latest/download/sheetstorm.tar.gz`.
   - **Source:** `git pull && docker compose up -d --build`.
   - **Source checkout on release images:** `git checkout vX.Y.Z`, set
     `SHEETSTORM_VERSION=X.Y.Z`, then `docker compose pull && docker compose up -d`.

The backend applies database migrations on start and refuses to run against a
schema it could not migrate (the container exits; check `docker compose logs
backend`). `flask sheetstorm repair-orphans` reports rows that can block a
migration.

## Backups

```bash
scripts/backup.sh                 # -> backups/sheetstorm-backup-<UTC>/
scripts/backup.sh /srv/backups    # another parent directory
```

The script works on a running stack and writes, with owner-only permissions:

| File | Contents |
|---|---|
| `database.dump` | `pg_dump` custom-format dump, taken inside the database container (its version always matches the server) |
| `artifacts.tar` | The evidence volume (`artifacts_data`) |
| `manifest.json` | Time, schema (Alembic) revision, app version, git commit, SHA-256 of each file |

The database dump is one consistent snapshot. The evidence volume is copied
after it, so every file the dump references is in the archive.

**Not in the backup:**

- **`.env`.** Store it separately and securely. Without the original
  `FERNET_KEY`, stored integration credentials cannot be decrypted. Without
  `CUSTODY_SIGNING_KEY` and `AUDIT_CHAIN_KEY`, custody and audit signatures
  cannot be verified.
- **Redis.** It holds only sessions, token revocations and rate-limit
  counters, so users sign in again after a restore.
- **Evidence in S3 or Google Drive.** Back it up at the provider.

Schedule it with cron, for example daily at 02:30 with a 14-day retention:

```cron
30 2 * * * cd /opt/sheetstorm && scripts/backup.sh /srv/backups >/dev/null && find /srv/backups -maxdepth 1 -name 'sheetstorm-backup-*' -mtime +14 -exec rm -rf {} +
```

The dump holds case data: keep backups encrypted at rest and off the host.

## Restoring

```bash
scripts/restore.sh backups/sheetstorm-backup-20261010T120000Z --yes
```

**Destructive.** The current database and evidence volume are replaced. The
script:

1. verifies the manifest checksums;
2. checks that this SheetStorm version knows the backup's schema revision (a
   backup from a newer version is refused before anything changes);
3. stops the application services;
4. recreates the database and restores the dump in a single transaction;
5. replaces the evidence volume;
6. starts the stack. The backend migrates a backup from an older version
   forward.
7. verifies the audit hash chain.

Restore with the **same secrets** the backup was taken with. If the audit
chain does not verify afterwards (exit code 3), the data is restored but
`AUDIT_CHAIN_KEY` / `AUDIT_CHAIN_PREVIOUS_KEYS` do not match the original
deployment.

**Moving to another host:** copy the backup directory and `.env`, start the
stack once (`docker compose up -d`), then run `scripts/restore.sh`.

CI runs a full backup, `down -v` and restore round trip on every change and
compares every table's row count and every evidence file's hash
(`ci/backup-roundtrip.sh`).

## Releases (maintainers)

1. Move the `## Unreleased` notes in `CHANGELOG.md` under `## X.Y.Z (YYYY-MM-DD)`
   and merge that to `main`.
2. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`. A tag with a
   suffix (`vX.Y.Z-rc.1`) makes a prerelease: no `X.Y` or `latest` tags,
   and the notes may come from `Unreleased`.
3. `.github/workflows/release.yml` then:
   - builds every image natively for amd64 and arm64;
   - pushes them with SBOM and provenance;
   - creates the multi-arch tags;
   - attests each image;
   - publishes the GitHub Release.

Run the workflow manually with `dry_run` to check that every image builds for
both platforms without publishing anything.
