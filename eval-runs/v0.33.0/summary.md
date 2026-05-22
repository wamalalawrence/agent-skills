# v0.33.0 — Lifecycle Wrappers Everywhere

This release responds to field feedback that agents can read a skill and still skip the required
workflow when the task feels small. The fix reduces friction and adds explicit compliance receipts
across every skill.

## Scope of the release

- `scripts/start-task.sh` now accepts no positional arguments. It auto-detects project and task id
  from `.agent-skills.yml`, `${PROJECTS_JSON}`, GitHub environment, branch name, or cwd, and accepts
  `--skill name=version` for blackboard attribution.
- New `scripts/finish-task.sh` writes the `Recent tasks` project-memory bullet, optional durable
  facts, telemetry, and cleanup in the correct order. Blocked and needs-context runs preserve
  scratch by default.
- Every `SKILL.md` now points to the same start/finish wrappers in its top preflight, includes a
  lifecycle receipt in its output contract, and removes the older duplicate bottom memory section.
- `software-engineer` adds a proportional `tiny` lane for mechanical changes. The lane reduces
  evidence volume, not required gates.
- Assistant and install docs now state that agents need access to `scripts/` as well as `skills/`.

## What was smoke-tested

Against a temporary `AGENT_SKILLS_CACHE_DIR`:

| Subject | Verified |
| --- | --- |
| `start-task.sh` with no args from repo cwd | Auto-detected project/task, created project memory, created blackboard |
| `start-task.sh --skill software-engineer=0.33.0` | Recorded skill version in blackboard |
| `finish-task.sh --summary ...` after no-arg start | Reused the persisted start context and cleaned the same task id |
| `start-task.sh <project> <url>` | Normalized URL-shaped task ids into safe cleanup keys |
| `finish-task.sh --summary ...` | Wrote `Recent tasks`, emitted telemetry, cleaned task scratch after memory write |
| `finish-task.sh --status blocked --summary ...` | Wrote memory and preserved per-task scratch |
| `run-evals.py` | Structural evals pass, including all-skills lifecycle compliance scenarios |
| `validate-repo.py` | Repository validation pass |

## Public-safety check

New evals use only placeholder repositories, task names, and file names. No private hosts, tokens,
customer data, or company-specific branch rules were added.
