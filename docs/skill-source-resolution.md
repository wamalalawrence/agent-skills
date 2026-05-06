# Skill-Source Resolution

`agent-skills` deliberately supports more than one place a skill file can live on disk. That
flexibility — a source repo plus a vendored copy plus a workspace symlink — gives users a clean
upgrade story across local-workspace and in-repo modes, but it also means an AI agent can see the
**same skill name in more than one directory** at the same time.

This page is the **single source of truth** for how an agent (and the human operator) must pick
**one** canonical skill directory. It applies to every skill in this repository and to every host
that loads them.

> **TL;DR:** if the current prompt gives an explicit skill directory or `SKILL.md` path, verify and
> use that path for this task. Otherwise, if there is a `.agent-skills.yml` with
> `skills.canonical_dir`, that wins. Then walk the resolution order below, pick the first match,
> and **stop**. Never load skills from two directories in the same task.

## Why this matters

A user who clones `agent-skills` next to other repos and runs `./setup.init` ends up with at
least two paths that contain the same `SKILL.md` files:

- `<workspace>/agent-skills/skills/...` — the source repo on disk.
- `<workspace>/.skills/...` — a symlink `setup.init` creates so workspace-aware assistants find
  skills at a stable path.

In `in-repo` mode the user may also commit a vendored copy at `<repo>/.agent-skills/skills/`
(for offline / cloud agents that cannot reach the source repo).

If the agent loads from both locations it can:

- pick the wrong version when one path is stale (e.g. a vendored copy frozen at `v0.16.0` while
  the source repo is at `v0.19.0`);
- merge contradictory instructions when two copies disagree;
- waste tokens reading the same workflow twice;
- silently prefer whichever directory its file-listing tool happens to return first.

The resolution order below removes that ambiguity.

## Resolution order

### Prompt-supplied source path

Before walking the generic resolution order, honor an explicit path supplied in the current user
prompt or task brief. The path may be absolute, relative to the current working directory, relative
to the repository root, or relative to `${WORKSPACE_ROOT}`. It may point at either the canonical
skills directory (`skills/`, `.skills/`, `.agent-skills/skills/`) or at a specific `SKILL.md`.

The agent must normalize the path, verify that it exists, and verify that the requested skill file
is present under it. If the user said "use `<path>/skills/software-engineer`", do not first search
only `<workspace>/.skills/software-engineer` and report failure. A host-specific default path is a
fallback, not evidence that the user-supplied path is missing.

If the explicit path cannot be read, stop with:

```text
Missing required setup: skill source not readable at <path>. I checked <resolved checks>.
```

Do not continue with a different copy unless the user explicitly authorizes the fallback. A wrong
skill source is a workflow blocker because it changes the instructions being executed.

The agent must walk this order **once per task**, top to bottom, and use the **first** directory
that satisfies the rule. Subsequent entries are ignored for the rest of the task.

1. **Configured canonical source.** If `.agent-skills.yml` exists at the workspace root (local
   mode) or repo root (in-repo mode) and declares `skills.canonical_dir`, resolve that path
   relative to the file and use it. This wins over every other rule.
2. **Repo-modification context.** If the current task is to modify the `agent-skills` repository
   itself (the working directory is the repo root, the user is editing files under `skills/`,
   or the prompt explicitly says "work on agent-skills"), use `<agent-skills-repo>/skills/`.
   This prevents an agent from "fixing" a skill via the installed copy and leaving the source
   repo untouched.
3. **In-repo vendored skills.** If `<repo>/.agent-skills/skills/` exists (the recommended layout
   for cloud / online agents that vendor a copy into the target repo), use it.
4. **Legacy workspace symlink.** If `<workspace>/.skills/` exists (the path `setup.init` creates
   in `local-workspace` mode), use it. Treat it as canonical for that workspace.
5. **Source repo fallback.** If only `<workspace>/agent-skills/skills/` exists (the user cloned
   the repo but has not run `setup.init` yet, or `--no-symlink` was passed), use it — but warn
   the operator once that running `./setup.init` will give them a stable `.skills` path.
6. **Multiple valid sources, none configured.** If two or more of rules 3-5 match and rule 1 did
   not select a winner, **stop and ask** the user which directory to use. Do not silently pick.
   Suggest the operator add `skills.canonical_dir` to `.agent-skills.yml` to make the choice
   explicit for future runs.

If none of the above match, the agent has no skills to load — report
`Missing required setup: no skill source found` and point the user at
[installation.md](installation.md).

## Owner-skill verification recipe

When a `delivery-planner` phase names a `recommended_owner` (e.g.
`test-automation-engineer`, `manual-tester`), the executing agent MUST verify
the owner skill is loadable **by reading the canonical path**, not by
consulting the host IDE's curated skill listing. Some IDEs surface only a
subset of installed skills (Claude Code shows the workspace registry; Cursor,
Continue, and similar surfaces may show a curated default), so an absence
from the IDE's "available skills" panel is **not** evidence the skill is
missing on disk.

The verification recipe (binding):

1. Resolve the canonical skill source per the order above. Common results
   are `<workspace>/.skills/`, `<repo>/.agent-skills/skills/`, or
   `<workspace>/agent-skills/skills/`.
2. Construct the candidate path:
   `<canonical>/<recommended_owner>/SKILL.md`.
3. Confirm the file exists and is readable (in shell:
   `test -r <path>`; in agents without shell, use the `Read` tool and
   verify the YAML header parses).
4. Confirm the loaded SKILL.md's `name` field equals `recommended_owner`.
   A path mismatch (e.g. directory renamed, vendored copy out of sync) is
   a blocker, not a substitution opportunity.

If steps 1–4 succeed, **load that file directly** with the agent's file-read
tool and follow its workflow for the phase. Do NOT downgrade to "execute the
phase directly" because the host's skill registry didn't surface the name.
Do NOT substitute a related skill (`software-engineer` is not an acceptable
substitute for `test-automation-engineer`).

If any step fails, stop with:

```text
BLOCKED: recommended owner skill unavailable
  recommended_owner: <name>
  canonical source: <path>
  paths checked: <list>
  reason: <one-line cause>
```

Record the same paths and reason on `phases[<id>].blocked_reason` in
`evidence-pack.yml`. The operator's next action is to fix the skill source
(rerun `./setup.init`, sync the vendored copy, or pass an explicit
`<path>` in the prompt), not to ask the agent to proceed without the skill.

This rule applies equally when the user invokes a skill outside a
`delivery-planner` phase: a prompt that names `recommended_owner: foo`
demands `foo`, regardless of host UI.

## Duplicate-handling rules

When a skill name appears in more than one of the directories listed above, the agent must
follow these rules — they apply even when the canonical source has been chosen:

- **Do not merge** instructions from two copies. Pick one `SKILL.md` and load only that one.
- **Do not load all copies** "to be safe". Two copies that drift will produce contradictory
  guidance and waste tokens.
- **Do not pick arbitrarily.** Use the resolution order above. If it does not pick a winner,
  ask.
- **Prefer the configured canonical source.** Rule 1 always wins, even if a later directory is
  newer.
- **Compare versions when metadata exists.** Each `SKILL.md` declares `metadata.version`. When
  two copies for the same skill name resolve under the canonical directory's tree (e.g. a
  vendored sub-tree), prefer the one whose `metadata.version` matches the workspace
  `.agent-skills.lock` file (see below). If neither matches, prefer the higher semver.
- **Warn on version drift.** When the chosen skill's `metadata.version` differs from a copy
  the agent rejected, surface a one-line warning in the agent's output:
  `skill drift: <name> v<a> chosen, v<b> ignored at <path>`. Do not block on this — surface
  it so the operator can decide whether to upgrade or remove the stale copy.

## How `setup.init` makes this deterministic

After `./setup.init`, the workspace contains a single small lock file the agent can read
without inspecting the source repo:

```text
<workspace>/.agent-skills.lock
```

The lock file is JSON, gitignored, and contains:

- `version` — the `VERSION` of the `agent-skills` repo at install/update time.
- `git_sha` — the source repo commit SHA at install/update time, when available.
- `canonical_dir` — the absolute path the agent should treat as the canonical skill source.
- `source_repo_dir` — the absolute path of the `agent-skills` source repo on disk, when known.
- `installed_at` — ISO-8601 timestamp of the most recent `setup.init` write.
- `installed_by` — `setup.init <version>` for traceability.

The lock file is **advisory**, not authoritative. Rule 1 (`.agent-skills.yml` ->
`skills.canonical_dir`) still wins. The lock file lets an agent pin to a known version and
detect drift on its own.

`setup.init --verify` re-reads the lock file, compares it against what is on disk, and reports
ambiguity (multiple skill sources without a configured canonical), staleness (lock file
`version` older than `agent-skills/VERSION`), or breakage (the canonical path does not exist).

## Mode-specific defaults

The shipped templates are deliberately conservative so existing users keep working:

| Mode             | Default `canonical_dir`                            | Why                                                     |
| ---------------- | -------------------------------------------------- | ------------------------------------------------------- |
| `local-workspace`| `.skills` (the symlink `setup.init` creates)       | Stable workspace path that survives moving the repo.    |
| `in-repo`        | `.agent-skills/skills` (vendored into the repo)    | Works for offline cloud agents with no sibling repo.    |
| Repo development | `skills` (the source `skills/` folder in this repo)| Lets contributors edit the canonical source directly.   |

These defaults match the resolution order above. A user who wants to override any of them sets
`skills.canonical_dir` explicitly.

## Operator quick reference

- "Use this exact skill folder" — provide the path in the prompt. The agent must verify that path
  first and must not fall back to `.skills` until you authorize it.
- "I want one explicit answer" — set `skills.canonical_dir` in `.agent-skills.yml` to the
  directory you want.
- "I just cloned and ran `setup.init`" — `.skills` is your canonical source.
- "I am working on `agent-skills` itself" — the source repo's `skills/` folder is canonical.
- "My agent reports drift" — run `./setup.init --update` (see [updates.md](updates.md)) or
  remove the stale vendored copy.
- "My agent reports ambiguity" — set `skills.canonical_dir`, or remove the directory you do not
  want the agent to use.

## Related

- [installation.md](installation.md) — how `.skills` is created and where the lock file lives.
- [execution-modes.md](execution-modes.md) — local-workspace vs. in-repo mode.
- [updates.md](updates.md) — how the user notices and applies new releases.
- [.agent-skills.example.yml](../.agent-skills.example.yml) — the `skills:` config block.
