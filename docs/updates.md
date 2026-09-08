# Updates

Releases follow [semver](versioning.md) and ship as git tags (`v0.36.0`, `v0.37.0`, …) with matching
GitHub releases. This page covers noticing a new release and applying it without losing local state.

## How an update flows

```text
GitHub release  --tag-->  origin  --git fetch-->  the source clone
                                                       |
                                                       |  agent-skills update
                                                       v
                                        one canonical tree under AGENT_SKILLS_HOME
                                                       |
                                    (host adapters already point here; nothing to re-copy)
                                                       v
                                        the next task uses the new skills
```

The source of truth is the git tag. Everything downstream — the canonical trees, the per-host
symlinks, the manifest — is derived from the clone on disk. Because host registrations are symlinks
into one tree, updating the clone updates every host at once. Nothing is copied, so nothing can go
stale independently.

## Check

```bash
agent-skills check-updates
```

Compares local `VERSION` against the latest release tag on `origin` using `git ls-remote --tags`, and
compares the local commit against `origin/<branch>`. Reports `up to date`, `update available` with
the version delta, or `ahead / detached` for a contributor checkout.

Exit codes: `0` up-to-date or ahead, `10` update available, `2` setup error. The distinct `10` makes
it scriptable in a shell prompt or CI smoke check without being confused with a generic failure.

Read-only. It does not fetch objects, modify the working tree, or touch the install.

## Apply

```bash
agent-skills update
agent-skills update --branch main   # track a branch instead of the latest tag
```

This:

1. Refuses if the clone's working tree is dirty. No silent overwrites.
2. Runs `git fetch --tags origin`.
3. Checks out the latest release tag, or the branch you named.
4. Re-runs the global install to refresh the canonical trees, host registrations, and manifest.
5. Prints the new release's `CHANGELOG.md` section so you can see what changed before your next task.

`update` is opt-in. It never runs on its own, never writes to `origin`, and never pushes anything.

### What update guarantees

- **One canonical source** is moved; there is no second copy to synchronise.
- **Host adapters keep pointing at it.** Registrations are refreshed idempotently, so a rerun neither
  duplicates a skill nor leaves a stale link.
- **Credentials are untouched.** They live in the OS credential store and the user config directory,
  neither of which the installer rewrites.
- **Project bindings are untouched.**
- **No repository is modified.** Update touches the clone and your home directory, never a project
  you work on.
- **Skills you installed yourself survive.** Only links resolving into the install root are managed.
- **Lock and version metadata are rewritten**, so drift detection is accurate afterwards.

## Manual update

```bash
cd /path/to/agent-skills
git fetch --tags origin
git checkout v0.37.0
./setup.init                 # refresh the install after a manual checkout
```

This is the contributor path. Most users should prefer `agent-skills update` because it includes the
dirty-tree check, the install refresh, and the changelog excerpt.

If you `git pull` and forget the refresh, nothing breaks — the canonical trees are symlinks, so the
new skills are live immediately. Only the manifest goes stale, which `verify` reports as drift.

## Drift detection

```bash
agent-skills verify
```

Compares the manifest against what is on disk and reports:

- **version drift** — the manifest says `v0.36.0` and the source tree says `v0.37.0`. Expected right
  after a manual `git pull`; fixed by `./setup.init`.
- **a broken canonical link** — the clone was moved or deleted. Reinstall repairs it.
- **a missing or foreign host registration** — a host directory lost a link, or something else owns
  that name. Reported per host.
- **legacy remnants** — a pre-v0.37.0 `.skills` or `.agent-skills.lock` beside the clone.

Per-task, an agent that loads a `SKILL.md` compares its `metadata.version` against the installed
version and surfaces one line when they disagree:

```text
skill drift: <name> v<a> chosen, v<b> ignored at <path>
```

Warnings, not blockers. Skills keep working with the version they loaded; the point is to make skew
**visible** rather than silent. Under a global install the common causes are a stale vendored copy in
some repository and an un-refreshed manifest.

## Cloud and in-repo updates

Cloud agents do not run the installer. A vendored copy is updated the way any vendored dependency is:

- **git submodule** — `git submodule update --remote --merge`, then commit the new SHA.
- **subtree or copy** — re-run whatever script vendored `skills/` in, and commit the diff.
- **reference-only** — nothing to update; the next message picks up the current version.

`scripts/check-updates.py` works in this mode. Point it at the vendored directory:

```bash
python3 scripts/check-updates.py --vendored .agent-skills/skills
```

It reads the vendored `metadata.version`, queries GitHub for the latest release tag (unauthenticated,
which works for public repos within the rate limit; pass `--token` to lift it), and reports `up to
date` / `update available` / `ahead`. No git checkout required.

### CI smoke check

```yaml
# .github/workflows/skills-update-check.yml (in your downstream repo)
on:
  schedule:
    - cron: "0 9 * * 1"
  workflow_dispatch:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 .agent-skills/scripts/check-updates.py --vendored .agent-skills/skills
        continue-on-error: true
```

Treat exit `10` as informational. The recommendation is **not** to fail CI on stale skills — surface
the warning and let the team upgrade on its own cadence.

## Legacy workspace updates

An install that predates v0.37.0 keeps its update path:

```bash
cd agent-skills
./setup.init --update --workspace-root /path/to/work
```

Values in `.env` outside the marker block are preserved verbatim, and Jira / Confluence / Sonar
credentials inside the block survive the rerun — that behaviour is covered by
`scripts/test-setup-update-preserves-credentials.sh`. An inherited `WORKSPACE_ROOT` pointing at a
directory with a `.env` also selects this path, so an existing script keeps working.

To move to the global install, see
[installation.md](installation.md#upgrading-from-v036x-workspace-installation).

## Watching for releases

- **GitHub notifications.** Repo → `Watch` → `Custom` → `Releases`.
- **RSS / Atom.** `https://github.com/wamalalawrence/agent-skills/releases.atom`.
- **`gh` CLI.** `gh release list --repo wamalalawrence/agent-skills --limit 5`.

## Rollback

```bash
cd /path/to/agent-skills
git fetch --tags origin
git checkout v0.36.0
./setup.init
```

Symmetric with update. The manifest is rewritten to the rolled-back version so the next task does not
warn about drift.

## What does not change on update

- Credential identities and their stored secrets.
- Project bindings.
- `.cache/agent-skills/...` in any repository — that is per-task evidence, not config.
- Legacy `.env` values outside the marker block.
- Vendored copies in other repositories. Only the source clone and the install are refreshed.
- Skills you installed yourself in a host directory.

## Related

- [Installation](installation.md) — first install and migration.
- [Skill-source resolution](skill-source-resolution.md) — which directory an agent loads, and how the
  manifest is consulted.
- [Versioning](versioning.md) — what a version number promises before 1.0.
- [Release checklist](release-checklist.md) — the maintainer steps that produce a release.
