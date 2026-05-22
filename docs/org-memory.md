# Org memory

Org memory is the third memory tier in the
[Company Brain](company-brain.md). It sits above per-project memory and
captures patterns, rules, and decisions that have been **confirmed in more
than one project** in the workspace. It is the corpus callosum that makes
specialist skills compound across the whole codebase, not just one repo.

## Layout

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/
  _org/
    memory.md       # human-readable accumulated cross-project knowledge
    memory.json     # structured mirror
    index.json      # cross-project index (project <-> shared libraries, ...)
```

The `_org/` prefix is reserved. The cleanup contract in
[`scripts/project-memory.py`](../scripts/project-memory.py) refuses any path
starting with `_`, so org memory survives every per-task cleanup pass for
every project.

## Default sections in `memory.md`

- **Org patterns** — engineering conventions confirmed across projects.
- **Shared libraries** — facts about libraries multiple projects depend on.
- **Common gotchas** — recurring failure modes worth warning the next agent
  about regardless of which project it is on.
- **Cross-project decisions** — ADR-shaped notes whose scope is the
  workspace, not a single repo.
- **Outcomes** — cross-project patterns lifted from
  `scripts/outcome-recorder.py --promote-to-org`.

## When to write to org memory

Org memory is **not** the default place to write. The default is the project
memory of the project the current task touches. A fact moves into org memory
only when at least one of these is true:

- The same fact has been confirmed in `≥ 2` projects (see
  [`scripts/promote-rules.py`](../scripts/promote-rules.py)).
- The fact is workspace-wide by construction (e.g. "all our services use the
  same internal auth contract") and would be misleading if scoped to one
  project.
- The same outcome (`reverted` / `hotfixed`) has occurred across projects with
  the same root cause and you want every future task on every project to see
  the lesson on read.

Promotion is explicit:

```bash
python3 scripts/org-memory.py promote \
  --from <source-project> \
  --section "Common gotchas" \
  --text "Migrations that touch tenancy must run through ${SHARED_LIBRARY_NAMES} review"
```

The source project is recorded as provenance so the org bullet always names
where the original observation came from.

## Cross-project index

`_org/index.json` is a lookup table:

```json
{
  "projects": {
    "acme-checkout": {"shared_libraries": ["auth-core", "tenant-context"]},
    "acme-billing":  {"shared_libraries": ["auth-core"]}
  },
  "shared_libraries": {
    "auth-core":      ["acme-billing", "acme-checkout"],
    "tenant-context": ["acme-checkout"]
  }
}
```

This is what makes the `software-engineer` "cross-project impact" step real
instead of wishful. Update it whenever a project's shared-library set changes:

```bash
python3 scripts/org-memory.py index-update acme-checkout \
  --shared-lib auth-core --shared-lib tenant-context
```

Query it from any skill before approving a change to a shared module:

```bash
python3 scripts/org-memory.py index-show --shared-lib auth-core
```

## When skills must read org memory

Every skill MUST, before any context discovery and before reading project
memory:

```bash
python3 scripts/org-memory.py read || true
```

A non-zero exit means org memory has not been created yet — proceed. If the
skill writes anything to org memory, it must do so via the `promote`,
`note`, or `index-update` subcommands so provenance and `updated_at` stay
consistent.

## What does not belong

- Secrets, tokens, PII — same rule as project memory.
- Per-project facts that have not been confirmed elsewhere — those live in
  the relevant `_projects/<slug>/memory.md`.
- Per-task scratch — that lives in the [task blackboard](task-blackboard.md).

## Cross-references

- [Company Brain](company-brain.md) — the overall loop.
- [Project memory](project-memory.md) — the per-project tier.
- [Task blackboard](task-blackboard.md) — the per-task tier.
- [`scripts/org-memory.py`](../scripts/org-memory.py) — the implementation.
- [`scripts/promote-rules.py`](../scripts/promote-rules.py) — promotion
  candidate scanner.
