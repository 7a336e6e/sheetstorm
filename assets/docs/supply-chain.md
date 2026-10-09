# Supply-Chain Security Policy

SheetStorm is a public DFIR tool. A compromised dependency would run on
responders' laptops and inside the containers that hold case evidence, so
dependency hygiene is treated as a security control, not housekeeping.

This policy exists because of self-propagating registry worms such as
**Shai-Hulud** (npm, Sept 2025), **Sha1-Hulud: The Second Coming** (npm,
Nov 2025) and their 2026 successors (Mini Shai-Hulud / TeamPCP on npm + PyPI,
the axios and `@bitwarden/cli` hijacks, the keyv/cacheable "ChainDrop" wave).
They share one pattern: a maintainer account or CI token is stolen, a new
version is published with a `preinstall`/`postinstall` script, and that script
harvests npm/GitHub/cloud tokens (often by running TruffleHog over `$HOME`),
exfiltrates them to attacker-created public GitHub repos, and republishes
itself into every package the victim can publish. Most malicious versions are
detected and unpublished within hours to a few days.

## Rules

### 1. Lockfile-only installs

- Install with `npm ci` (frontend) and hash-locked `pip install --require-hashes`
  (Python). Never run a bare `npm install` / `pip install <pkg>` in Docker,
  CI, or for a routine local setup.
- `package-lock.json` must be committed and must resolve everything from
  `registry.npmjs.org` with an `integrity` hash. Git/URL/tarball dependencies
  are not allowed (`allow-git=none`).
- Frontend installs need `--legacy-peer-deps` (current peer-dependency
  conflicts): `npm ci --ignore-scripts --legacy-peer-deps`.

### 2. No install scripts (allowlist only)

- `frontend/.npmrc` (and the root `.npmrc`) set `ignore-scripts=true`, and the
  Dockerfile also passes `--ignore-scripts` explicitly.
- Verified on 2026-10-08: nothing in the frontend tree needs an install
  script. Packages that declare one and why it is safe to skip:

  | Package | Script | Why it can be skipped |
  |---|---|---|
  | `unrs-resolver` | `postinstall: napi-postinstall ... check` | Prebuilt binary ships as an optional dependency (`@unrs/resolver-binding-*`); the script only checks for it |
  | `fsevents` (macOS, optional) | implicit `node-gyp` (binding.gyp) | Ships a prebuilt `fsevents.node` |
  | `msw` (root `shadcn` CLI only) | `postinstall` copies a service worker | Not used by the app |

  `next` (`@next/swc-*`) and `sharp` (`@img/sharp-*`) use per-platform
  optional dependencies and have no install scripts. `tsc --noEmit`, `eslint`,
  `next build` and the Docker image build all pass with scripts disabled.
- If a future dependency genuinely needs a build step, allowlist it
  explicitly and visibly (e.g. `RUN npm rebuild <pkg>` in the Dockerfile with
  a comment saying why) after vetting it. Never turn scripts back on globally.

### 3. Exact pins and a release-age cooldown

- `save-exact=true`: new dependencies are written without `^`/`~`.
- Any new or bumped dependency version must be **at least 7 days old**
  (14 days for a new major or a brand-new package). `.npmrc` enforces this
  for `npm install`/`npm update` through `min-release-age=7` (npm >= 11.10).
  On older npm, pass a date explicitly:
  `npm install <pkg>@<ver> --before="$(date -u -v-7d +%F)"` (macOS) or
  `--before="$(date -u -d '7 days ago' +%F)"` (Linux).
  `npm ci` ignores the cooldown (it installs exactly what the lockfile says),
  so the check has to happen when the lockfile changes.
  Commands that look up registry metadata for already-locked versions
  (`npm audit signatures`, `npm outdated`, `npm view`) fail with `ETARGET`
  while the lockfile holds a version younger than the cooldown; run them with
  `--min-release-age=0`.
- For Python, `scripts/lock-python.sh` resolves with
  `uv pip compile --exclude-newer <date 7 days ago>` (section 5).
- **Security-fix exceptions.** If an advisory is fixed only in a release that
  is younger than the cooldown, pin that exact version, record it in the table
  below (package, version, advisory id, date to re-verify with OSV), and move
  to a release past the cooldown as soon as one exists.

  | Package | Version | Advisory | Re-verify |
  |---|---|---|---|
  | _none currently_ | | | |

  2026-10-08: `next`/`eslint-config-next` are pinned to `16.3.8` (published
  2026-09-30, past the cooldown), which fixes GHSA-2xp9-vwfh-vxw4,
  GHSA-p293-qw3h-jr36 and GHSA-vcvr-r3jv-pc5j (critical RCEs) and every other
  Next.js advisory OSV lists for 16.x, so the younger `16.4.0` was not needed.
- Dependabot (`.github/dependabot.yml`) opens PRs only for versions past a
  7-day cooldown and covers npm, pip (backend, mcp-server, mcp-bridge),
  Dockerfiles, docker-compose and GitHub Actions. For npm, Docker,
  docker-compose and Actions, version updates arrive as one grouped weekly PR
  of minor/patch bumps per ecosystem/directory (at most 2 open per entry);
  semver-major bumps are ignored and done manually. Security updates are
  grouped into one PR per ecosystem/directory. The pip entries are
  security-only (`open-pull-requests-limit: 0` disables version updates):
  Python deps are hash-locked and Dependabot does not regenerate the `*.lock`
  files, so routine pip bumps are done by hand with `scripts/lock-python.sh`
  (section 5), and pip security PRs also need a relock before merging.

### 4. Vetting checklist for a new or bumped dependency

Before adding a dependency or merging a bump:

1. **Need**: can existing code or a dependency we already have do it?
2. **Age**: is the version at least 7 days old (14 for new packages/majors)?
3. **Maintainers**: who publishes it? Any maintainer or ownership change,
   new publisher, or a long-dormant package that suddenly released?
4. **Popularity and source**: real download numbers, a linked source repo
   that matches the published tarball, a name that is not a typosquat.
5. **Install scripts**: does the version declare `preinstall`/`install`/
   `postinstall` or ship a `binding.gyp`? Treat a newly added script as a
   red flag.
6. **Advisories**: check OSV (`osv-scanner` or https://osv.dev), the GitHub
   Advisory Database (malware advisories), and Socket.dev or Aikido Intel for
   the exact version. Any `MAL-` entry blocks the change.
7. **Diff**: for bumps of sensitive packages, look at the published diff
   (e.g. `npm diff --diff=<pkg>@<old> --diff=<pkg>@<new>`).
8. **Lockfile review**: the PR's lockfile diff should contain only the
   packages you expected.

### 5. Hash-locked Python

- Each Python component keeps a **human-edited input** (exact `==` pins) and a
  **generated lockfile** with a sha256 for every artifact of every pinned
  version. Only the inputs are edited by hand; the locks are committed.

  | Input (edit) | Lockfile (generated) | Used by |
  |---|---|---|
  | `backend/requirements.txt` | `backend/requirements.lock` | backend image |
  | `backend/requirements-dev.txt` (`-r requirements.txt` + pytest) | `backend/requirements-dev.lock` | backend `test` stage, local dev |
  | `mcp-server/constraints.txt` | `mcp-server/requirements.lock` | mcp-server image |
  | `mcp-server/build-requirements.txt` (hatchling) | `mcp-server/build-requirements.lock` | wheel build (`--no-build-isolation`) |
  | `mcp-server/{constraints,requirements-dev,build-requirements}.txt` | `mcp-server/requirements-dev.lock` | local dev / tests |
  | `mcp-bridge/requirements.txt` | `mcp-bridge/requirements.lock` | `setup.sh`, user installs |
  | `mcp-bridge/requirements{,-dev}.txt` | `mcp-bridge/requirements-dev.lock` | local dev / tests |

- `scripts/lock-python.sh` regenerates every lock with
  `uv pip compile --generate-hashes --universal --exclude-newer <7 days ago>`
  inside a throwaway, digest-pinned uv container (nothing installed on the
  host, no host credentials passed in). `--exclude-newer` hides every file
  uploaded after the cutoff, so a lock cannot pick up a release younger than
  the cooldown, including transitive dependencies. Locks are universal: they
  carry the hashes for linux/amd64, linux/arm64 and developer platforms
  (backend/mcp-server resolved for CPython >= 3.12, the bridge for >= 3.11).
  Dev locks are constrained to the runtime lock, so shared packages never drift.
- Dockerfiles install with
  `pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r requirements.lock`,
  then run `pip install --no-index --no-deps -r <input>` (fails the build if
  the input was edited without regenerating the lock - the pip analogue of
  `npm ci` refusing an out-of-sync lockfile) and `pip check`.
  Everything currently installs from wheels, so the images carry no compiler
  or `-dev` headers. If a package ever has no wheel for a target platform,
  list it explicitly with `--no-binary <pkg>` and note it in the Dockerfile.
- Local installs use the same locks:
  `pip install --require-hashes --no-deps -r requirements-dev.lock`.

#### How to add or bump a Python dependency

1. Vet the version (section 4) and make sure it is at least 7 days old.
2. Edit the **input** file only (e.g. `backend/requirements.txt`), keeping an
   exact `==` pin.
3. Recompile the locks: `scripts/lock-python.sh` (cutoff defaults to 7 days
   ago; `EXCLUDE_NEWER=YYYY-MM-DD scripts/lock-python.sh` to pin a date). If
   the version you asked for is younger than the cutoff, resolution fails -
   wait, or follow the documented-exception rule in section 3.
4. Review the lock diff (`git diff -- '*.lock'`): only the package you meant to
   change and the transitive dependencies it really needs should move. Check
   any new transitive package against section 4 and OSV.
5. Rebuild and test: `docker compose build backend mcp-server`,
   `backend/tests/run_in_docker.sh`, and the component's own tests.
6. Commit the input and the lock together. Dependabot PRs (pip) only edit the
   input files; check such a PR out, run step 3 and push the regenerated lock
   before merging (the Docker build fails until you do).

### 6. Digest-pinned container images

- Every `FROM` and every `image:` in `docker-compose.yml` is pinned as
  `name:tag@sha256:<multi-arch index digest>`. Dependabot updates the digest.
- Resolve a digest with
  `docker buildx imagetools inspect <name:tag> --format '{{json .Manifest}}'`
  and use the top-level (index) digest.

### 7. No credentials in the install environment

- Run installs (`npm ci`, `pip install`, `docker build`) in a shell **without**
  `NPM_TOKEN`, `GITHUB_TOKEN`/`GH_TOKEN`, `AWS_*`, `GOOGLE_APPLICATION_CREDENTIALS`,
  Azure or Supabase keys exported. Do not keep long-lived publish tokens in
  `~/.npmrc`.
- Docker builds receive only public `NEXT_PUBLIC_*` build args. `.env*`
  (and `*.pem`/`*.key` in frontend/backend) are excluded by each component's
  `.dockerignore`; never `COPY` them.
- `.env` and `.mcp.json` hold live secrets and are git-ignored. Prefer
  `${env:VAR}` substitution in `.mcp.json` over inline tokens.
- In future CI: least-privilege `permissions:`, actions pinned by commit SHA,
  no `pull_request_target` with checkout of PR code, npm publishing (if ever)
  via trusted publishing (OIDC), not tokens.

### 8. Recommended (optional) tools

- **OSV-Scanner**: `osv-scanner scan source -r .` scans every lockfile against
  OSV, including `MAL-` malicious-package entries.
- **Socket Firewall** (`sfw npm ci ...`) or **Aikido Safe Chain**
  (`safe-chain` wrapping npm/pip): block known-malicious packages at install
  time.
- `npm audit signatures --min-release-age=0` verifies registry signatures and
  provenance attestations for the installed tree.

## Incident playbook: a compromised version is detected

If a lockfile, `node_modules`, a venv, an image, or the npm cache contains a
version listed as malicious (OSV `MAL-`, GHSA malware advisory, vendor IOC
list), or you find worm artifacts:

1. **Isolate.** Stop installs and builds. Disconnect the affected machine or
   runner from the network if the payload may have run. Do not run `npm`,
   `pip` or `docker build` again on it.
2. **Preserve evidence before cleaning.** Copy (do not delete): the lockfile,
   the affected package directory, `~/.npm/_logs`, `~/.npm/_cacache` index,
   shell history, and any of these artifacts: `setup_bun.js`,
   `bun_environment.js`, `bundle.js` containing TruffleHog strings,
   `truffleSecrets.json`, `cloud.json`, `contents.json`, `environment.json`,
   `actionsSecrets.json`, `~/.truffler-cache`, unexpected `~/.bun`,
   self-hosted runner directories (`~/actions-runner`, `.dev-env`), and new
   `.github/workflows/*` files (e.g. `shai-hulud-workflow.yml`,
   `discussion.yaml`, `formatter_*.yml`). Note timestamps.
3. **Rotate every credential reachable from that machine or job**, from a
   clean device, starting with the ones that allow propagation:
   - npm tokens (revoke all; re-enable 2FA for publish)
   - GitHub PATs, OAuth apps, SSH keys, `gh` tokens, Actions secrets
   - cloud credentials (AWS/GCP/Azure), Supabase service-role and anon keys
   - everything in `.env` (`SECRET_KEY`, `JWT_SECRET_KEY`, `FERNET_KEY`
     after data re-encryption planning, OAuth client secrets, AI API keys,
     Slack webhook, `GITHUB_PAT`, `MCP_AUTH_TOKEN`, admin password)
   - every token in `.mcp.json` (GitHub, ClickUp, Supabase, etc.)
4. **Hunt for exfiltration and propagation on GitHub.** Check the account and
   orgs for new repositories named or described "Shai-Hulud", "Sha1-Hulud",
   "The Second Coming" or random names containing `data.json`,
   `environment.json` or `contents.json`; unexpected branches named
   `shai-hulud`; new workflows; new self-hosted runners; new deploy keys or
   OAuth grants; and the security log for token use from unknown IPs. Check
   npm for versions you did not publish.
5. **Clean rebuild.** Remove `node_modules`, venvs and the npm cache only after
   evidence is preserved; pin to a known-good version; reinstall with
   `npm ci --ignore-scripts` / hash-locked pip; rebuild images with
   `--no-cache`.
6. **Disclose.** If anything could have reached SheetStorm users (a published
   image or release), publish an advisory per [SECURITY.md](../../SECURITY.md).
