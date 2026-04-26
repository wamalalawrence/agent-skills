# Skill Performance Review

Manual review for target release `v0.8.0`, performed against the scenarios in [`evals/`](../evals/)
and the multi-skill workflows described below. This is a maintainer review note, not a benchmark or
proof that any model will behave correctly.

## Review Summary

All six skills produced likely useful output during manual review. The main risks
found and the fixes made were:

- `issue-investigator`: mode detection was less consistent than other skills.
  Fix: added `AGENT_SKILLS_MODE` handling and a behavior checklist.
- `software-engineer`: wording leaned too much on Jira/GitHub and one heading
  casing differed. Fix: generalized issue-source wording, normalized
  `When To Use`, and added a behavior checklist.
- `code-reviewer`: mode detection was less consistent than the main engineering
  skill. Fix: added `AGENT_SKILLS_MODE` handling and a behavior checklist.
- `product-owner`: bug-flavored refinement could sound fix-ready before root
  cause was known. Fix: clarified that unknown-root-cause work should become
  investigation/discovery, not a fix-ready story.
- `manual-tester`: output contract was strong, but the behavior checklist was
  implicit. Fix: added a behavior checklist focused on evidence, environment,
  defects, and handoff.
- `test-automation-engineer`: the 20-run flake budget could be unrealistic when
  CI/tooling is unavailable. Fix: softened into a default target with
  lower-confidence fallback and a visible follow-up.

## Per-Skill Findings

### Issue Investigator

- Useful output: likely, because it forces expected vs actual behavior, evidence, reproduction, root
  cause status, confidence, and next action.
- Too vague: no major gap after review.
- Over-prescriptive: safe reproduction and evidence-pack persistence are strict, but appropriate for
  bug/root-cause work.
- Stopping behavior: clear `unknown` root-cause status and missing-context stops.
- Hallucination prevention: strong; root-cause claims require evidence.
- Related skills: correctly hands implementation to `software-engineer`, review to `code-reviewer`,
  product ambiguity to `product-owner`, manual evidence to `manual-tester`, and regression coverage to
  `test-automation-engineer`.
- Output/workflow match: yes.
- Contradictions: none found.
- Unrealistic assumptions: Jira access is optional when direct issue details are supplied.
- Fixes made: mode detection aligned with other skills and behavior checklist added.

### Software Engineer

- Useful output: likely, because it combines context discovery, plan, implementation, validation,
  review, and final synthesis.
- Too vague: no major gap after review.
- Over-prescriptive: bugfix failing-test-first is strict but intentionally gates speculative fixes.
- Stopping behavior: clear `needs-context` and `blocked` paths.
- Hallucination prevention: strong; validation, tests, review, and root cause cannot be claimed
  without evidence.
- Related skills: correctly reuses `issue-investigator`, `code-reviewer`, `product-owner`,
  `manual-tester`, and `test-automation-engineer`.
- Output/workflow match: yes.
- Contradictions: the section casing was inconsistent with the required section list.
- Unrealistic assumptions: issue-source wording was too Jira-specific in a few places.
- Fixes made: generalized issue-source wording, fixed `When To Use`, and added behavior checklist.

### Code Reviewer

- Useful output: likely, because it requires issue alignment before generic quality review.
- Too vague: no major gap after review.
- Over-prescriptive: hard handoff contract is strict, but it prevents generic PR approvals.
- Stopping behavior: clear `NEEDS_CONTEXT` and `NOT_REVIEWABLE` verdicts.
- Hallucination prevention: strong; it must not invent issue context or test results.
- Related skills: correctly invokes `issue-investigator` when context is missing and uses
  `software-engineer` standards for implementation quality.
- Output/workflow match: yes.
- Contradictions: none found.
- Unrealistic assumptions: repository-aware review requires setup, but manual supplied-diff review
  can continue with disclosed limits.
- Fixes made: mode detection aligned with other skills and behavior checklist added.

### Product Owner

- Useful output: likely, especially for refining vague work into testable scope.
- Too vague: no major gap after review.
- Over-prescriptive: negative acceptance criteria requirement is strict but valuable for quality.
- Stopping behavior: clear; unresolved goal, value, expected behavior, or feasibility risk blocks
  Jira-ready output.
- Hallucination prevention: strong; stakeholder priorities, analytics, legal rules, and approvals
  cannot be invented.
- Related skills: correctly routes bugs to `issue-investigator`, feasibility to `software-engineer`,
  scenario coverage to `manual-tester`, and automation-friendly ACs to `test-automation-engineer`.
- Output/workflow match: yes.
- Contradictions: support-complaint example needed softer wording to avoid skipping investigation.
- Unrealistic assumptions: no excessive Jira dependency; Jira-ready output is a format, not a tool
  requirement.
- Fixes made: clarified unknown-root-cause work as investigation/discovery and updated example
  prompt.

### Manual Tester

- Useful output: likely, because it emphasizes environment, build, role, data, expected vs actual,
  evidence, defects, retest, and automation candidates.
- Too vague: no major gap after review.
- Over-prescriptive: commit SHA requirement may be unavailable for casual users, but the skill lets
  unknown material context block or lower confidence.
- Stopping behavior: clear when expected behavior, scope, environment, or data are missing.
- Hallucination prevention: strong; it cannot claim tested environments or complete validation by
  assumption.
- Related skills: correctly uses `product-owner`, `software-engineer`, `issue-investigator`, and
  `test-automation-engineer`.
- Output/workflow match: yes.
- Contradictions: none found.
- Unrealistic assumptions: no private systems required.
- Fixes made: behavior checklist added.

### Test Automation Engineer

- Useful output: likely, because it gates automation on value, repeatability, observability, and
  stability.
- Too vague: no major gap after review.
- Over-prescriptive: repeat-run flake budget was too absolute for small or tool-limited projects.
- Stopping behavior: clear when expected behavior, stable reproduction, fixtures, selectors, or CI
  ownership are missing.
- Hallucination prevention: strong; it cannot claim tests or repeat-run checks without execution.
- Related skills: correctly consumes product, manual, investigation, engineering, and review inputs.
- Output/workflow match: yes.
- Contradictions: none found.
- Unrealistic assumptions: CI repeat-run requirement needed a practical fallback.
- Fixes made: flake budget wording now allows strongest feasible stability checks with disclosed
  lower confidence and visible follow-up.

## Multi-Skill Workflow Review

### Workflow A: Bug Fix

`issue-investigator` -> `software-engineer` -> `code-reviewer` -> `test-automation-engineer`

- Investigator establishes expected vs actual behavior, root-cause status, confidence, and safe
  reproduction evidence.
- Engineer does not implement until enough evidence exists and plans a failing regression test for
  bug fixes.
- Reviewer checks issue alignment, root-cause fit, engineering quality, tests, and Definition of
  Done evidence.
- Automation engineer converts only stable, reproducible behavior into regression coverage.

Result: coherent after the flake-budget and behavior-checklist updates.

### Workflow B: Feature Delivery

`product-owner` -> `software-engineer` -> `manual-tester` -> `test-automation-engineer`

- Product owner defines goal, scope, acceptance criteria, negative criteria, and handoff notes.
- Engineer implements against clarified requirements and stops when intent or validation is missing.
- Manual tester validates workflows, edge cases, negative paths, environment, defects, and retest.
- Automation engineer converts stable high-value checks into maintainable automated tests.

Result: coherent after clarifying bug-flavored product work and adding behavior checklists.

### Workflow C: PR Review

`code-reviewer` -> `issue-investigator` if context missing -> `software-engineer` if fix guidance is
needed

- Reviewer performs issue-aware review when context exists and does not invent missing tickets.
- Reviewer sends unclear expected behavior/root cause to `issue-investigator` before final verdict.
- Reviewer can recommend fix direction, while implementation remains with `software-engineer`
  unless the user explicitly asks for edits.

Result: coherent after aligning mode detection and adding the reviewer behavior checklist.
