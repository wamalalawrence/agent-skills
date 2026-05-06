# Project memory

Project memory is the small, durable Markdown note an agent updates after every successful task
on a project, and reads first when starting the **next** task on the same project. It exists so
that every fresh agent session does not pay the same discovery cost — "what runtime does this
repo use?", "which Maven module owns the public API?", "why does the integration suite need
`--profile docker-it`?" — that the previous session already paid.

It pairs with the per-task evidence pack but lives outside it: per-task scratch is cleaned up
when the task completes; project memory is preserved and updated.

## Layout

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/
  _projects/<project-slug>/
    memory.md          # human-readable accumulated knowledge (the source of truth)
    memory.json        # structured mirror, updated by scripts/project-memory.py
  <issue-key>/         # per-task evidence pack — cleaned up on task completion
```

The `_projects/` prefix is reserved. No issue key may begin with `_`. The cleanup tool refuses
to delete anything matching `_*` so project memory is never collateral damage during task
cleanup.

## When skills must read project memory

Every top-level skill that touches a repository must, **before any other context discovery**:

1. Resolve the project name from `${PROJECTS_JSON}` (local-workspace) or the `project:` block
   in `.agent-skills.yml` (in-repo).
2. Run `python3 scripts/project-memory.py read <project>` (or read the file directly at the
   resolved path). A non-zero exit means no memory exists yet — proceed to step 3.
3. If no memory exists yet, run
   `python3 scripts/project-memory.py init <project> --repo <owner/repo>` to write the skeleton
   before context discovery starts. Recording even an empty skeleton makes the cleanup contract
   well-defined for downstream skills.
4. Treat what is written there as **starting context**, not gospel. If the recorded fact is
   contradicted by evidence in the current run, update the note with the corrected fact rather
   than silently ignoring the stale one.

## What belongs in project memory

Short, durable, project-scoped facts. Examples that are appropriate:

- Build & runtime: language version, package manager, "always run X before Y".
- Module layout: which directory holds the public API, which holds tests, which is generated.
- Test invocation: profile flags (`-Pintegration`, `--profile docker-it`), Testcontainers needs.
- Common gotchas: "node_modules must be regenerated after schema bump", "the e2e suite skips
  unless `STAGE_BASE_URL` is exported".
- Cross-cutting links: the canonical SonarQube project key, the CI workflow name that gates PRs.
- Recent tasks: a one-line bullet per completed task (date, issue key, one-sentence outcome).

What does **not** belong:

- Secrets, tokens, API keys — they live in `.env` / host secret manager, never here.
- Customer data, PII, or anything from a non-local environment.
- Per-task working notes — those belong in the issue-keyed evidence pack.
- Speculative plans for future work — those belong in `delivery-planner` artifacts.

## What gets cleaned up after a task completes

When a task reaches a terminal state (`done` after PR opened, `blocked`, or explicitly abandoned):

1. The agent writes the final updates to project memory **first** — at minimum a `Recent tasks`
   bullet, plus any new "Build & runtime" or "Common gotchas" facts the task surfaced.
2. Then the agent runs `python3 scripts/project-memory.py cleanup-task <issue-key>`. This:
   - Deletes `${cache_root}/<issue-key>/` and everything below it.
   - Refuses any path starting with `_` or containing `..` or `/`.
   - Does **not** touch `_projects/`.
3. Local feature branches that have been merged and pushed are then safe to delete with
   `git branch -d <branch>` (caller's responsibility — the script does not run git). Branches
   for `blocked` or in-flight work are **not** deleted.
4. Remote branches are never deleted by this contract; that is reserved for the user.

The order matters. Recording memory before deleting the task scratch is what guarantees the
knowledge survives.

## Updating memory mid-task

Skills should append a note as soon as a fact is verified, not at the end. Use:

```bash
python3 scripts/project-memory.py note <project> \
  --section "Build & runtime" \
  --text "Module ./api requires sdk@21 and 'mvn -pl api verify' (NOT 'mvn verify')"
```

The script timestamps every note and keeps both `memory.md` (for humans) and `memory.json`
(for tooling) in sync.

## Why this is separate from per-task evidence packs

Per-task evidence packs answer: "for *this* ticket, what did I learn and decide?" They are
verbose, ticket-shaped, and worth deleting once the PR merges.

Project memory answers: "for *this* repo, what should every future agent know up front?" It is
short, deduplicated, and worth keeping forever — including across `setup.init --update`,
across vendored copies, and across agents from different IDEs.

Mixing the two means either the per-task pack grows forever or the durable knowledge is lost
on cleanup. Keeping them separate gives both lifecycles what they need.

## Cross-references

- [Auth discovery](auth-discovery.md) — config-file location order; project memory should
  record any non-default location it had to discover.
- [GitHub access ladder](github-access.md) — record per-project GitHub account preference
  in project memory once verified.
- [`scripts/project-memory.py`](../scripts/project-memory.py) — the implementation.
- [Software-engineer SKILL.md](../skills/software-engineer/SKILL.md) — the
  read-on-start / write-on-finish contract for code-changing work.
