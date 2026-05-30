# v0.34.0 — Delivery Runner (Autonomous Phase Handoff)

Minor release adding the `delivery-runner` skill: an autonomous executor that
walks a `delivery-planner` phased plan to completion, opening a fresh,
empty-context agent for each phase and verifying every phase from the persisted
plan artifacts rather than from chat. This release also realigns all skill
`metadata.version` values with `VERSION` after the `0.33.2` patch drifted them.

## Scope of the release

- New top-level skill `skills/delivery-runner/` (SKILL.md, README.md, and the
  `handoff-prompt-template.md` + `run-loop-checklist.md` references).
- New read-only helper `scripts/delivery-run-next.py` — the deterministic
  dispatch-decision spine the loop calls each iteration.
- Dispatcher framing added to `docs/review-loops.md` (the runner sits outside the
  cross-skill review loops; each dispatched phase is the root of its own
  depth-two chain).
- `delivery-planner` cross-references the runner for end-to-end execution.
- `VERSION`, README status, and every `SKILL.md` `metadata.version` bumped to
  `0.34.0`.
- New eval `evals/delivery-runner-autonomous-handoff.md`.

## What was smoke-tested

`scripts/delivery-run-next.py` was exercised against temporary plan-index
fixtures covering the decision branches the loop depends on:

| Subject | Verified |
| --- | --- |
| Dispatchable plan (pointer `ready`, prereqs done) | `action: dispatch` with correct phase id, owner, and resolved `phase_file` |
| Pointer with an unmet prerequisite | `action: stop`, `reason: prerequisites-unmet` |
| All phases done | `action: stop`, `reason: complete` |
| `BLOCKED` readiness / null pointer | `action: stop`, `reason: needs-human` |
| Missing index path | `action: error`, exit code 2 (caller surfaces, does not loop) |
| Input as cache dir, phased-plan dir, or index file | all three resolve to the same index |
| `validate-repo.py` | repository validation passes |

The autonomous multi-agent loop itself is a runtime behavior that structural
validation cannot prove end-to-end; the eval scenario
`evals/delivery-runner-autonomous-handoff.md` captures the expected and
anti-expected behavior (fresh-agent dispatch, artifact-based verification, clean
stop on a blocked phase, no spinning) for behavioral review. See
[docs/known-limitations.md](../../docs/known-limitations.md).

## Public-safety check

- No secrets, private tokens, private hostnames, local absolute paths, or real
  customer data introduced.
- Examples use placeholder work keys (`EXAMPLE-200`, `PROJ-1234`) and generic
  systems.
