# Project Memory Eval: Read On Start, Update On Finish, Survive Cleanup

## Input Context

A workspace has been used for two prior tasks on the same project, `example-api`. Project
memory at
`~/work/.cache/agent-skills/_projects/example-api/memory.md` already contains:

```markdown
# Project memory: example-api

- Repo: acme-corp/example-api
- Created: 2026-04-12T08:00:00Z

## Project facts
- Java service, Maven multi-module, 3 modules (api, core, integration-tests).

## Build & runtime
- Java 21 via sdkman; `sdk use java 21.0.4-tem` before any `mvn` call.
- Integration suite needs `--profile docker-it` AND a running local Postgres.

## Common gotchas
- The `core` module regenerates Avro classes — run `mvn -pl core generate-sources`
  before opening the files in the IDE or imports look broken.

## Recent tasks
- (2026-04-12) ABC-101: bumped postgres driver to 42.7.4. PR #812.
- (2026-04-19) ABC-130: fixed null-handling in OrderMapper. PR #834.
```

The user now asks the agent to "investigate and fix `ABC-156` — a flaky integration test in
`example-api`". The agent's cwd is `~/work/example-api`. There is no per-task `.cache/agent-skills/ABC-156/`
yet.

## Skill Under Test

`software-engineer` (with `issue-investigator` invoked from Phase 1). The same read-on-start /
write-on-finish contract applies to every top-level skill.

## Why This Scenario

This eval pins three behaviors at once:

1. **Read-on-start.** The agent must surface the recorded `Common gotchas` (Avro generation,
   `--profile docker-it`) before re-discovering them. Re-discovery wastes tokens and frequently
   produces the wrong diagnosis ("the test is flaky" when in fact the agent forgot the
   profile flag).
2. **Mid-task append.** Any new durable fact discovered during the run (e.g. "the integration
   suite shares the test-orders DB with `core`'s unit tests, so parallel execution flakes")
   must be appended to project memory while the work is in flight, not at the end.
3. **Survive cleanup.** When the task completes, the agent runs
   `python3 scripts/project-memory.py cleanup-task ABC-156`. That deletes
   `~/work/.cache/agent-skills/ABC-156/` only. The `_projects/example-api/` directory and
   `memory.md` must still exist afterwards, and a new `Recent tasks` bullet for `ABC-156`
   must be present in `memory.md` before the cleanup ran.

## Expected Behavior

Phase 1, before context discovery:

- The agent runs `python3 scripts/project-memory.py read example-api` and includes the
  `Common gotchas` lines in its requirement-understanding block (it knows about Avro
  generation and the `docker-it` profile without re-discovering them).
- The agent uses `--profile docker-it` on its first reproduction attempt, not after a wasted
  cycle of "the test imports don't compile".

Mid-task:

- When the agent verifies a new durable fact (the parallel-execution flake), it runs:
  ```bash
  python3 scripts/project-memory.py note example-api \
    --section "Common gotchas" \
    --text "Integration suite shares test-orders DB with core unit tests; do not run in parallel."
  ```
- The new bullet appears in `memory.md` immediately, with an ISO timestamp.

End of task (after the PR is open):

- The agent appends a `Recent tasks` bullet:
  `- (2026-05-06) ABC-156: serialised integration suite to remove parallel-DB flake. PR #901.`
- The agent runs `python3 scripts/project-memory.py cleanup-task ABC-156`. The output is
  `removed: ~/work/.cache/agent-skills/ABC-156`.
- `~/work/.cache/agent-skills/_projects/example-api/memory.md` **still exists** and contains
  both the new `Common gotchas` line and the new `Recent tasks` bullet.
- For local feature branches that are merged and pushed, the agent runs
  `git branch -d <branch>` (never `-D`); branches that are not merged are left alone.

## Anti-Patterns This Eval Pins

- Skipping the read-on-start step and re-discovering the Avro / `docker-it` facts.
- Writing recurring runtime facts into the per-task `<issue-key>/evidence-pack.yml` instead of
  project memory (where the next task can find them).
- Writing secrets, tokens, environment URLs, or customer data into project memory.
- Running cleanup **before** appending project memory — the script is correct, but the order
  loses knowledge.
- Calling `cleanup-task _projects` or `cleanup-task ../something` — the script must refuse,
  and the agent must not retry with a workaround.
- Deleting the local branch before the PR is merged, or deleting the remote branch at all.

## Required Output

The skill output must include two structured traces:

```
project-memory: read example-api -> 4 sections, 2 recent tasks
project-memory: appended Common gotchas (1 note), appended Recent tasks (1 note)
project-memory: cleanup-task ABC-156 -> removed
```

and the post-run filesystem state must match the layout described above.
