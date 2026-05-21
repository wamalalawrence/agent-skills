# v0.31.0 — Company Brain Foundations

This release turns the eight specialist skills into a self-improving loop:
every task writes to a per-task blackboard, every PR's fate is recorded as an
outcome, every recurring lesson can be promoted into org-tier memory, and a
telemetry layer makes "the skills are improving" a number instead of a
feeling.

The full loop is documented in
[`docs/company-brain.md`](../../docs/company-brain.md).

## Scope of the release

- Added third memory tier: org memory (`scripts/org-memory.py`,
  `docs/org-memory.md`) with the project ↔ shared-library cross-project index.
- Added per-task shared working memory: blackboard
  (`scripts/blackboard.py`, `docs/task-blackboard.md`) with `facts`,
  `assumptions`, `unknowns`, `decisions`, `artifacts`, `handoffs`, and
  `skill_versions` for honest attribution.
- Added outcome feedback closer: `scripts/outcome-recorder.py` writes PR
  outcomes into project memory's `Outcomes`, emits a telemetry `outcome`
  event, and (for `reverted` / `hotfixed`) writes an automatic `Lesson`
  bullet into project memory's `Common gotchas`. Optional explicit promotion
  to org memory requires `--confirmed-in N>=2`.
- Added telemetry: `scripts/telemetry.py` writes one NDJSON event per line
  per project under `_projects/<slug>/telemetry.ndjson`.
- Added rule-promotion scanner: `scripts/promote-rules.py` surfaces bullets
  that recur across `≥ --min-projects` projects so a human can review and
  promote them into org memory and/or a SKILL.md checklist.
- Added eval harness: `scripts/run-evals.py` enforces structural contracts on
  every eval file and on every per-release `eval-runs/<version>/summary.md`.
- Extended `scripts/project-memory.py` with `dedup`, `compact --keep N`,
  `search <query>`, and `promote-candidates --section --min-count`
  subcommands.
- Added a "Company Brain integration" section to all eight top-level
  SKILL.md files (5-step hook list pointing at the new scripts).
- Bumped `VERSION` and all eight SKILL.md `metadata.version` to `0.31.0`.

## What was smoke-tested

Against a temporary `AGENT_SKILLS_CACHE_DIR`:

| Subject | Verified |
| --- | --- |
| `org-memory.py init / note / index-update / index-show` | ✅ |
| `project-memory.py init / note / dedup / search` | ✅ (dedup removed 1 duplicate bullet) |
| `blackboard.py init / append / handoff / read` | ✅ |
| `telemetry.py emit / report` | ✅ (reports per-skill event counts) |
| `outcome-recorder.py record` (merged) | ✅ (no auto-lesson) |
| `outcome-recorder.py record` (reverted) | ✅ (auto-lesson written into `Common gotchas`) |
| `outcome-recorder.py list` | ✅ |
| `promote-rules.py` | ✅ (emits JSON candidate list) |
| `run-evals.py` | ✅ (`28 files, 8 skills known, 0 failures, 0 warnings`) |
| `validate-repo.py` | ✅ (`ok: repository validation passed`) |

No model-in-the-loop eval is part of this release — `run-evals.py` is the
structural regression layer. A future iteration can plug a real agent runner
behind `--invoke`.

## Public-safety check

All new files contain only placeholder hostnames, ticket keys, and project
slugs (`acme-checkout`, `acme-billing`, `ABC-123`, `ABC-124`). No real
customer, employee, or tenant identifiers.
