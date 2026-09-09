# Skill-Source Resolution

An agent can see the same skill name in more than one directory at once. This page is the **single
source of truth** for picking **one**.

> **TL;DR:** if the prompt names a skill directory, verify and use it. Otherwise, if you are
> modifying `agent-skills` itself, use the source repo. Otherwise walk the order below, take the
> first match, and **stop**. Never load one skill from two directories in the same task.

## Why more than one exists

Since v0.37.0 the local answer is normally singular: one global install, one canonical tree at
`${AGENT_SKILLS_HOME}/skills`, reached through per-host symlinks. Every host path resolves to the
same physical directory.

Multiplicity still arises legitimately:

- **Host directories that scan each other.** Cursor reads four global directories; VS Code reads
  three. One host can list a skill several times. Because every registration is a symlink to the
  canonical tree, those are the same file at the same version.
- **A vendored copy in the target repository**, for cloud agents that cannot reach your machine.
  This one *can* be a different version, and that is the case the rules below exist for.
- **The source clone**, when you are working on `agent-skills` itself.
- **A legacy workspace** from before v0.37.0: `<workspace>/.skills` and a sibling clone.

The danger was never duplication. It was **version skew**: loading a vendored copy frozen at
`v0.19.0` while the install is at `v0.37.0`, or merging two copies that disagree.

## Resolution order

Walk this **once per task**, top to bottom, and use the **first** directory that satisfies the rule.
Later entries are then ignored for the rest of the task.

### 0. Prompt-supplied source path

Honour an explicit path from the current prompt or task brief before anything else. It may be
absolute, relative to the working directory, or relative to the repository root, and it may point at
a skills directory or a specific `SKILL.md`.

Normalise it, verify it exists, and verify the requested skill is present under it. If the user said
"use `<path>/skills/software-engineer`", do not search a default location first and report failure. A
host default is a fallback, not evidence the user's path is missing.

If the explicit path cannot be read, stop:

```text
Missing required setup: skill source not readable at <path>. I checked <resolved checks>.
```

Do not silently continue with a different copy. A wrong skill source changes the instructions being
executed.

### 1. Configured canonical source

If `.agent-skills.yml` declares `skills.canonical_dir`, resolve it relative to that file and use it.
This wins over every rule below. It is the escape hatch for any layout this page does not anticipate.

### 2. Repo-modification context

If the task is to modify the `agent-skills` repository itself — the working directory is that repo,
the user is editing files under `skills/`, or the prompt says so — use `<agent-skills-repo>/skills/`.

This is deliberately above the global install. Without it, an agent "fixes" a skill through the
installed symlink and leaves the source repo untouched, or edits the canonical tree without a commit
to show for it.

### 3. Project-vendored skills

If `<repo>/.agent-skills/skills/` exists, use it. This is the recommended layout for cloud and
offline agents, and a repository that vendored a copy did so on purpose.

Be aware of what this means: a vendored copy **silently outranks the global install**, so cloning a
repository can change the instruction set an agent executes. Before v0.37.0 that combination stopped
and asked. It no longer does, because in the layouts this rule exists to serve — cloud runners,
offline machines — stopping was the wrong answer far more often than it was the right one.

The mitigations are drift detection below, and the fact that these files are visible in the
repository's own diff. Treat an unexpected `.agent-skills/skills/` in a repository you do not
control the same way you would treat an unexpected CI workflow change.

### 4. Global canonical install

`${AGENT_SKILLS_HOME}/skills` — the default `~/.agent-skills/skills`. This is the normal answer for
local work, and it is what every host registration points at.

An agent that reached a skill through `~/.claude/skills/<name>` or `~/.agents/skills/<name>` is
already here: those are symlinks into this tree.

### 5. Legacy workspace sources

For installs that predate v0.37.0 and have not migrated:

In this order, so the rule stays decidable when both are present:

1. `<workspace>/.skills/` — the symlink pre-v0.37 setup created. Preferred, because it is what
   that installer actually pointed agents at.
2. `<workspace>/agent-skills/skills/` — a sibling clone with no symlink. The fallback for a
   workspace whose symlink was never created or has since been deleted.

Both still work. Surface a one-line note that installation is now machine-global and
`agent-skills migrate` explains the move. Do not block on it.

### 6. Nothing found

Report `Missing required setup: no skill source found` and point at
[installation.md](installation.md).

## Removed in v0.37.0

The old rule "two or more sources match and none is configured ⇒ stop and ask" is gone. It existed
because `.skills`, a sibling clone, and a vendored copy were genuinely ambiguous, and the operator
was the only one who could break the tie.

The order above is now total, including inside rule 5, where the two legacy sources are ranked
against each other rather than listed side by side. There is always a first match, so there is
nothing to ask about. Keeping an ambiguity rule that can no longer fire would be historical baggage
that teaches agents to stop when they should proceed.

What remains is drift detection, below. That was always the part with real value.

## Duplicate handling and drift

These apply even after a canonical source is chosen.

- **Do not merge.** Pick one `SKILL.md` and load only that one. Two copies that disagree are not two
  halves of an instruction.
- **Resolve to a physical path before comparing.** Two paths that resolve to the same directory are
  one source, not two. This is the normal case across host directories and must not be reported as a
  conflict.
- **Compare versions when copies genuinely differ.** Each `SKILL.md` declares `metadata.version`.
  Prefer the one matching the installed version from `${AGENT_SKILLS_HOME}/install.json`; failing
  that, prefer the higher semver.
- **Warn on drift, do not block.** When the chosen skill's version differs from a copy you rejected,
  emit one line:

  ```text
  skill drift: <name> v<a> chosen, v<b> ignored at <path>
  ```

  The operator decides whether to upgrade or delete the stale copy. Blocking would strand anyone
  mid-migration.

## What the install records

```text
${AGENT_SKILLS_HOME}/install.json
```

JSON, readable without inspecting the source repo:

- `version` — the installed release.
- `git_sha` — the source commit at install time, when available.
- `source_dir` — the source tree the install points at.
- `canonical_skills_dir` — the path rule 4 uses.
- `hosts` — which host integrations were registered.
- `installed_at`, `installed_by` — traceability.

It is **advisory**. Rule 1 still wins. Its job is to let an agent pin a version and notice drift on
its own.

```bash
agent-skills verify
```

re-reads the manifest, checks every host registration resolves to the canonical tree, and reports
drift between the manifest and the source tree.

### Legacy lock file

Pre-v0.37.0 workspaces have `<workspace>/.agent-skills.lock` with a similar shape. Still read when
present; `agent-skills migrate` reports it as obsolete once the global install exists.

## Mode defaults

| Mode | Canonical source | Why |
| --- | --- | --- |
| `global` | `${AGENT_SKILLS_HOME}/skills` | One install, every local repository. |
| `in-repo` | `<repo>/.agent-skills/skills` | Works for cloud agents that cannot see your machine. |
| Repo development | the source `skills/` folder | Contributors edit the canonical source directly. |
| `local-workspace` (legacy) | `<workspace>/.skills` | Existing installs keep working. |

Override any of them with `skills.canonical_dir`.

## Owner-skill verification recipe

When a `delivery-planner` phase names a `recommended_owner`, the executing agent MUST verify the
owner skill by **reading the canonical path**, not by consulting the host's skill listing. Some hosts
surface only a subset, so an absence from a panel is **not** evidence the skill is missing on disk.

Binding recipe:

1. Resolve the canonical source per the order above. Under a global install that is
   `${AGENT_SKILLS_HOME}/skills`.
2. Construct `<canonical>/<recommended_owner>/SKILL.md`.
3. Confirm it exists and is readable (`test -r <path>`, or a `Read` tool plus a frontmatter parse).
4. Confirm the loaded `name` field equals `recommended_owner`. A mismatch is a blocker, not a
   substitution opportunity.

If steps 1-4 succeed, load that file directly and follow its workflow. Do **not** downgrade to
"execute the phase directly" because a host UI did not list the name, and do **not** substitute a
related skill — `software-engineer` is not an acceptable stand-in for `test-automation-engineer`.

On failure, stop with:

```text
BLOCKED: recommended owner skill unavailable
  recommended_owner: <name>
  canonical source: <path>
  paths checked: <list>
  reason: <one-line cause>
```

Record the same paths and reason on `phases[<id>].blocked_reason` in `evidence-pack.yml`. The
operator's next action is to fix the skill source (`agent-skills install`, `agent-skills verify`, sync the
vendored copy, or pass an explicit path), not to proceed without the skill.

This applies equally outside a `delivery-planner` phase: a prompt naming a skill demands that skill,
regardless of host UI.

## Operator quick reference

- "Use this exact folder" — put the path in the prompt. It outranks everything.
- "I want one explicit answer forever" — set `skills.canonical_dir` in `.agent-skills.yml`.
- "I just installed" — `${AGENT_SKILLS_HOME}/skills` is canonical. `agent-skills verify` confirms it.
- "I am working on `agent-skills` itself" — the source repo's `skills/` folder is canonical.
- "My agent reports drift" — `agent-skills update`, or delete the stale vendored copy.
- "A host lists a skill twice" — expected; both entries are the same file. `agent-skills verify`
  proves it.

## Related

- [Installation](installation.md) — the canonical tree and the manifest.
- [Assistants](assistants.md) — per-host discovery paths and duplicate-scan behaviour.
- [Execution modes](execution-modes.md) — global, in-repo, and legacy workspace.
- [Updates](updates.md) — how a new release reaches the canonical source.
- [`.agent-skills.example.yml`](../.agent-skills.example.yml) — the `skills:` config block.
