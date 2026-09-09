# Updates, rollback, and channels

Releases follow [semver](versioning.md) and ship as git tags (`v0.42.0`, `v0.43.0`, …) with matching
GitHub releases. This page covers noticing a new release, applying it without losing local state,
and undoing it when it turns out to be a mistake.

## How an update flows

```text
agent-skills update
        |
        v
  release provider          which release should I be on?
        |
        v
  download + stage          into cache/staging, nothing on the machine has changed yet
        |
        v
  verify                    the payload is the release it claims to be
        |
        v
  self-test                 the staged runtime answers before anything points at it
        |
        v
  ACTIVATE                  one atomic symlink swap: current -> versions/<new>
        |
        v
  reconcile hosts           registrations and Execution Guard hooks re-asserted
        |
        v
  verify machine            and if this fails, roll straight back
```

No source checkout is involved. Nothing is copied per host, because host registrations point at
`~/.agent-skills/skills`, which points at `current` — so activating a release moves every host at
once and there is no window in which two hosts disagree about the version.

## Check

```bash
agent-skills check-updates
agent-skills check-updates --json
```

Asks the release provider for the latest release on your channel and compares it against the active
version. Exit codes: `0` up to date or ahead, `10` update available, `2` usage error, `3`
authentication required, `4` the source was unreachable. The distinct `10` makes it scriptable in a
shell prompt or CI check without being confused with a failure.

Read-only. It downloads nothing and touches no installation.

## Apply

```bash
agent-skills update
agent-skills update --version 0.43.0     # a specific release
agent-skills update --channel rc         # follow release candidates too
```

`update` is opt-in. It never runs on its own, never writes to a remote, and never pushes anything.

### What update guarantees

- **A failed update changes nothing.** Everything before `ACTIVATE` happens in a staging directory.
  A download that fails, a payload whose hash does not match, or a release whose runtime cannot
  answer its own self-test all leave the previous release running.
- **A failed activation is undone.** If activation or host reconciliation fails, the previous release
  is re-activated and the hosts reconciled back to it.
- **No mixed installs.** Skills, runtime, and docs come from one version directory. `verify` asserts
  that the manifest, `current`, and the payload's own `VERSION` all agree, and fails if they do not.
- **The previous release is kept**, so `rollback` has somewhere to go.
- **Credentials and project bindings are untouched.** They live in the OS credential store and the
  user config directory, neither of which the installer rewrites.
- **No repository you work on is modified.**
- **Skills and hooks you installed yourself survive.** Only entries resolving into the install root
  are managed.
- **Execution Guard hooks stay coherent.** They point at `~/.agent-skills/bin/agent-skills`, which
  resolves through `current`, so enforcement and the skills it protects are always the same version.

### Downgrades are never a side effect

```bash
agent-skills update --version 0.42.0
# agent-skills: refusing to replace the active release 0.43.0 with the older 0.42.0
#   to go back deliberately:   agent-skills rollback --version 0.42.0
#   to force it anyway:        add --allow-downgrade
```

An update that quietly moves a machine backwards is how a downgrade attack lands a version whose
vulnerabilities are already published, and it is also just a bad surprise. Going backwards is
supported — it is called `rollback` — but never as a side effect of `update`.

## Rollback

```bash
agent-skills rollback                  # return to the release you were on before
agent-skills rollback --version 0.42.0 # a specific installed release
agent-skills versions                  # what is installed, and what is active
```

Rollback re-verifies the target payload before activating it, then reconciles host registrations and
Execution Guard hooks so they resolve to the release you went back to. It is an undo, not a time
machine: after rolling back, the rollback candidate is the release you rolled back *from*, so a
second rollback undoes the first rather than walking further into the past.

Two releases are retained by default. `--keep N` on install or update changes that.

## Channels

```bash
agent-skills update                  # stable
agent-skills update --channel rc     # release candidates as well
```

`stable` never offers a pre-release, so `1.0.0-rc.1` will not appear on a stable machine. `rc` is a
superset: someone tracking release candidates is still offered the stable release that supersedes the
last one.

The channel a machine is on is recorded in the install manifest and reported by
`agent-skills doctor`.

## Drift detection

```bash
agent-skills verify
```

Reports:

- **version drift** — the manifest, `current`, and the payload's `VERSION` disagree. A failure, not a
  warning: it means the installation is mixed. `agent-skills install` repairs it.
- **a broken activation pointer** — `current` points at a release that is no longer there.
  `agent-skills rollback` or a reinstall repairs it.
- **a missing or foreign host registration** — a host directory lost a link, or something else owns
  that name. Reported per host.
- **whether a rollback target exists**, because a recovery path you have never checked is not a
  recovery path.

Per-task, an agent that loads a `SKILL.md` compares its `metadata.version` against the installed
version and surfaces one line when they disagree:

```text
skill drift: <name> v<a> chosen, v<b> ignored at <path>
```

Warnings, not blockers. Skills keep working with the version they loaded; the point is to make skew
**visible** rather than silent. Under a global install the usual cause is a stale vendored copy in
some repository.

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

## Watching for releases

- **GitHub notifications.** Repo → `Watch` → `Custom` → `Releases`.
- **RSS / Atom.** `https://github.com/wamalalawrence/agent-skills/releases.atom`.
- **`gh` CLI.** `gh release list --repo wamalalawrence/agent-skills --limit 5`.

## What does not change on update

- Credential identities and their stored secrets.
- Project bindings.
- `.cache/agent-skills/...` in any repository — that is per-task evidence, not config.
- Any legacy `.env` you still have. Nothing writes it; the access resolver still reads it.
- Vendored copies in other repositories. Only this machine's installation is refreshed.
- Skills you installed yourself in a host directory.

## Related

- [Installation](installation.md) — first install and migration.
- [Skill-source resolution](skill-source-resolution.md) — which directory an agent loads, and how the
  manifest is consulted.
- [Versioning and exit codes](versioning.md) — what a version number promises before 1.0.
- [Release providers](release-providers.md) — where releases come from, and how they are verified.
- [Release checklist](release-checklist.md) — the maintainer steps that produce a release.
