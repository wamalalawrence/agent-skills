# Multi-Skill Eval: Bug To Regression Flow

## Input Context

A support report says users can submit duplicate refund requests by double-clicking the submit
button. The expected behavior is one refund request per order. The report includes anonymized steps,
one request id, and a timestamp. No root cause, code diff, or tests are supplied.

## Skill Under Test

`issue-investigator` -> `software-engineer` -> `code-reviewer` -> `test-automation-engineer`

## Expected Behavior

- `issue-investigator` establishes expected vs actual behavior, reproduction status, root-cause
  confidence, and safe evidence needs.
- `software-engineer` implements only after sufficient evidence and plans a failing regression test
  path for stable behavior.
- `code-reviewer` checks issue alignment, root-cause fit, duplicate-submit edge cases, test quality,
  and rollback/risk notes.
- `test-automation-engineer` proposes regression coverage only for deterministic, reproducible
  behavior and chooses the lowest reliable level.

## Required Output Fields

- Investigation result with root-cause status and missing evidence.
- Engineering result with plan, validation, tests, risks, and review handoff.
- Code review verdict with issue alignment and findings.
- Automation strategy with chosen level, flakiness risks, and CI plan.

## Must Not Do

- Must not let engineering skip investigation for an ambiguous production-like bug.
- Must not let review become generic when issue context is available.
- Must not automate a scenario before reproduction is stable.
- Must not invent private payment/refund system details.

## Pass/Fail Checklist

- [ ] Each skill owns its part of the workflow and does not duplicate another skill.
- [ ] Handoffs preserve expected behavior, actual behavior, evidence, and uncertainty.
- [ ] The fix path depends on sufficient investigation evidence.
- [ ] Review blocks or questions weak issue alignment.
- [ ] Automation scope is stable, valuable, and not brittle.