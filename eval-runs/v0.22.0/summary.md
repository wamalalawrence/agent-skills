# v0.22.0 — eval-runs summary

Two structural improvements land in v0.22.0:

1. **Bounded cross-skill review loops.** `software-engineer` already had explicit
   inner-/outer-loop review against `code-reviewer`. v0.22.0 extends the same idea — with
   strict, written termination rules — to `issue-investigator`, `product-owner`,
   `manual-tester`, and `test-automation-engineer`, and centralises the bounds in
   [`docs/review-loops.md`](../../docs/review-loops.md). See
   [`skill-review-loops.md`](skill-review-loops.md).
2. **Token-efficiency audit.** A repo-wide pass to confirm that `agent-skills` is cheap to
   load into agent context. See
   [`token-efficiency-audit.md`](token-efficiency-audit.md).

Bookkeeping: README "Status" pin moved to `0.22.0`; `VERSION` and every
`SKILL.md → metadata.version` bumped to `0.22.0`; `COVERAGE_TARGET_PERCENT`
documented as an *agent-resolved* placeholder so users do not waste time
overriding a value the agent never reads.

## Result

- `python3 scripts/validate-repo.py` and `python3 scripts/validate_skills.py` continue to
  pass with the same warning class as v0.21.0 (eval-run hostname / ticket-key warnings).
- All four newly-wired loops are bounded in writing by
  [`docs/review-loops.md`](../../docs/review-loops.md): one revision round, no recursion,
  depth cap of two skills. The existing `software-engineer` loop keeps its
  `${CODE_REVIEWER_MAX_ROUNDS}` cap (default `3`) as a documented exception.

## Why now

The user reported (1) a perceived README version mismatch, (2) uncertainty whether
`COVERAGE_TARGET_PERCENT` is actually consumed, (3) that several skills produced output
that was never reviewed by a peer skill, and (4) a request to audit the repo for
token efficiency. v0.22.0 addresses all four without introducing any endless-loop risk —
every new loop names its termination condition.
