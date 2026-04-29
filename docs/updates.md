# Updates

`agent-skills` releases follow [semver](versioning.md) and ship as git tags
(`v0.18.0`, `v0.19.0`, …) with matching GitHub releases. This page describes how a user who
has already cloned the repo notices a new release and applies it without losing local config
or breaking running skill sessions.

## How updates flow

```text
GitHub release  --tag-->  origin/main  --git fetch-->  local clone
                                                           |
                                                           |  ./setup.init --update
                                                           v
                                                  workspace .skills + .agent-skills.lock
                                                           |
                                                           v
                                                  next agent task uses the new skills
```

The source-of-truth is the git tag on GitHub. Everything downstream of that — the symlink, the
vendored copy, the lock file — is derived from the source repo on disk.

## Three update channels

### 1. `setup.init --check-updates` (recommended for most users)

```bash
cd agent-skills
./setup.init --check-updates
```

This:

- Compares the local `VERSION` file against the latest **release tag** on `origin` (using
  `git ls-remote --tags origin`, no extra dependencies, no GitHub token).
- Compares the local commit SHA on the current branch against `origin/<branch>`.
- Reports one of three statuses:
  - `up to date` — local is at the latest release tag and has no new commits.
  - `update available` — a newer release tag exists, with the version delta and a one-line
    summary of how to apply it.
  - `ahead / detached` — the local branch is ahead of the remote (likely a contributor
    workflow); the user is told no update is needed.
- Exits `0` for up-to-date, `10` for update-available, `2` for setup error. The `10` exit
  code makes it scriptable in a shell prompt or CI smoke check without confusing it with
  generic failure.

This is read-only. It does **not** fetch large objects, modify the working tree, or touch the
workspace.

### 2. `setup.init --update` (apply the latest release)

```bash
cd agent-skills
./setup.init --update
```

This:

1. Runs `--check-updates` first. If the working tree is dirty, the command stops and tells the
   user to commit or stash. No silent overwrites.
2. Runs `git fetch --tags origin`.
3. Checks out the latest release tag (or the configured branch if `--update --branch main` is
   passed).
4. Re-runs the normal `setup.init` flow non-interactively (`--yes`) against the same workspace
   root, **preserving** every value already in `.env` outside the marker block.
5. Rewrites `<workspace>/.agent-skills.lock` with the new `version`, `git_sha`, `installed_at`,
   and `canonical_dir`.
6. Prints a short changelog excerpt (the `## <new-version>` section from `CHANGELOG.md`) so the
   operator sees what changed before running their next task.

`--update` is **opt-in**. `setup.init` never auto-updates the user's clone, never writes to
`origin`, and never pushes anything.

### 3. Manual `git pull`

Power users can update the clone with normal git commands:

```bash
cd agent-skills
git fetch --tags origin
git checkout v0.19.0          # or: git pull origin main
./setup.init --yes            # refresh .skills and .agent-skills.lock
```

This is the path contributors take. It is documented for completeness, but most users should
use `--update` because it includes the dirty-tree check, the lock-file rewrite, and the
changelog excerpt.

## How the agent notices stale skills

Every task starts by reading `<workspace>/.agent-skills.lock` (or the in-repo equivalent).
The agent compares `lock.version` against the `metadata.version` of the chosen `SKILL.md` and
against the `VERSION` file in the source repo when the source repo is on disk.

- **Match** — proceed normally.
- **Skill ahead of lock** (`SKILL.md` declares a version newer than `lock.version`) — surface
  `skill drift: lock pinned to v<a>, loaded v<b>` and proceed using the loaded skill. This is
  expected right after a manual `git pull` before the user reruns `setup.init`.
- **Lock ahead of skill** — surface `skill drift: lock expects v<a>, loaded v<b> from
  <path>`. The user likely has a stale vendored copy. Point them at
  [skill-source-resolution.md](skill-source-resolution.md) and `--update`.
- **Source repo ahead of lock** — surface `update available: agent-skills v<a> -> v<b>`. The
  user pulled new code without rerunning setup.

These are warnings, not blockers. Skills keep working with the version they loaded. The point
is to make drift **visible** instead of silent.

## In-repo (cloud / online agent) updates

In-repo mode does not run `setup.init`. The user updates the vendored copy of `skills/` the
same way they update any other vendored dependency:

- **Git submodule.** `git submodule update --remote --merge` then commit the new submodule SHA.
- **Subtree / vendor copy.** Re-run the script that copied `skills/` in (typically a
  `make vendor-skills` or a one-line `rsync` in `scripts/`); commit the diff.
- **Reference-only.** If the agent loads `SKILL.md` files via URL (e.g. an attached file in a
  chat), there is nothing to update — the next message picks up the latest version.

`scripts/check-updates.py` works in this mode too. Point it at the vendored directory:

```bash
python3 scripts/check-updates.py --vendored .agent-skills/skills
```

It reads the vendored skills' `metadata.version`, queries GitHub for the latest release tag
(unauthenticated — works for public repos within the rate limit, or pass `--token $GITHUB_TOKEN`
to lift the limit), and reports `up to date` / `update available` / `ahead`. No git checkout
required.

## CI smoke check

Add a non-blocking weekly job that surfaces stale clones:

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

Treat the `10` exit code as informational. The maintainer's recommendation is **not** to fail
CI on stale skills — instead, surface the warning and let the team upgrade on their cadence.

## Watching for releases

For a passive notification stream (no clone polling required):

- **GitHub release notifications.** Open the repo on GitHub → `Watch` → `Custom` →
  `Releases`. You will receive an email or notification on each tagged release.
- **RSS / Atom.** `https://github.com/wamalalawrence/agent-skills/releases.atom` works in any
  feed reader.
- **`gh` CLI.** `gh release list --repo wamalalawrence/agent-skills --limit 5` prints the most
  recent five releases.

## Rollback

```bash
cd agent-skills
git fetch --tags origin
git checkout v0.18.0          # the version you want to roll back to
./setup.init --yes            # refresh .skills + .agent-skills.lock
```

Rollback is symmetric with update. The lock file is overwritten to reflect the rolled-back
version so the agent's next task does not warn about drift.

## What does not change on update

- `.env` values **outside** the setup marker block are preserved verbatim.
- `.jira-config.yml` is left alone (the user owns it after first creation).
- `.cache/agent-skills/...` is left alone (that is per-task evidence, not config).
- Vendored copies in **other** repos are not touched. Only the source clone and the workspace
  symlink are updated.

## Related

- [installation.md](installation.md) — first-time setup.
- [skill-source-resolution.md](skill-source-resolution.md) — which skill directory the agent
  must use, and how the lock file is consulted.
- [versioning.md](versioning.md) — how version numbers are assigned and what counts as a
  breaking change.
- [release-checklist.md](release-checklist.md) — the maintainer steps that produce a release.
