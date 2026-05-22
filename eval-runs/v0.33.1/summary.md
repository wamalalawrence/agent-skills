# v0.33.1 — Lifecycle Cache-Root Patch

Patch release for `v0.33.0`. During post-release closeout, the lifecycle wrappers exposed a
cache-root inconsistency: `start-task.sh` and `finish-task.sh` could default to different cache
roots when neither `AGENT_SKILLS_CACHE_DIR` nor `WORKSPACE_ROOT` was set. That made a no-arg finish
write memory to one cache while trying to clean scratch from another.

## Scope of the release

- Align `start-task.sh` default cache-root resolution with the Python memory scripts:
  `AGENT_SKILLS_CACHE_DIR` -> `WORKSPACE_ROOT/.cache/agent-skills` -> `cwd/.cache/agent-skills`.
- Make `finish-task.sh` pass the resolved cache root explicitly to `project-memory.py` and
  `telemetry.py`.
- Keep the persisted last-context behavior from `v0.33.0` so no-arg finish closes the same task id
  created by no-arg start.
- Bump `VERSION`, README status, and every `SKILL.md` metadata version to `0.33.1`.

## What was smoke-tested

Against a temporary `AGENT_SKILLS_CACHE_DIR`:

| Subject | Verified |
| --- | --- |
| `start-task.sh --skill manual-tester=0.33.1` followed by no-arg `finish-task.sh` | Finish reused the persisted task id and cleaned the same scratch directory |
| `finish-task.sh --status blocked` | Wrote memory and preserved scratch |
| `git diff --check` | Passed |
| `run-evals.py` | Structural evals pass |
| `validate-repo.py` | Repository validation pass |

## Public-safety check

No new private hosts, tokens, customer data, or company-specific branch rules were added.
