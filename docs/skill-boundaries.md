# Skill Boundaries

These skills are meant to collaborate, not compete. Each role owns a different decision surface and
must hand off when the task moves outside that surface.

| Skill | Owns | Does not own | Typical handoff |
| --- | --- | --- | --- |
| `software-engineer` | Repository context, implementation plan, code changes, validation, PR readiness | Product intent invention, standalone root-cause guessing, final human release approval | To `issue-investigator` for unclear bugs; to `code-reviewer` at review gates; to testing skills for validation coverage |
| `issue-investigator` | Issue classification, expected vs actual behavior, evidence, reproduction, root-cause status, next action | Implementing fixes, final PR verdicts, invented acceptance criteria | To `software-engineer` for fixes; to `product-owner` for unclear intended behavior; to `test-automation-engineer` for stable regressions |
| `code-reviewer` | Issue-aware diff review, engineering-quality findings, severity/confidence, final review verdict | Writing the implementation unless asked, guessing issue intent, generic formatting review | To `issue-investigator` when ticket/root-cause context is unclear; to `software-engineer` for fixes |
| `product-owner` | Product goal, user value, scope, acceptance criteria, UX notes, Jira-ready handoff | Technical architecture, code review, test implementation, deciding bug root cause | To `issue-investigator` for bug-flavored input; to `software-engineer` for feasibility; to testing skills for coverage concerns |
| `manual-tester` | Manual test scope, scenarios, execution results, defect evidence, retest guidance, automation candidates | Root-cause analysis, product intent invention, automation implementation | To `issue-investigator` for reproducible defects; to `product-owner` for unclear expected behavior; to `test-automation-engineer` for stable regression candidates |
| `test-automation-engineer` | Automation strategy, test level choice, fixtures, selectors/contracts, CI artifacts, flakiness risk | Automating unclear behavior, manual exploration, product intent, root-cause investigation | To `manual-tester` for unstable/manual scenarios; to `issue-investigator` for repro evidence; to `code-reviewer` for test-quality review |

## Required Handoffs

- `software-engineer` must use `issue-investigator` when expected behavior, issue context, or root
  cause is unclear.
- `software-engineer` must use `code-reviewer` after implementation and again before final PR or
  release handoff.
- `code-reviewer` must use `issue-investigator` when correctness depends on ticket understanding or
  root-cause evidence that is missing.
- `product-owner` must route support complaints, incidents, regressions, and other bug-flavored
  requirements through `issue-investigator` before writing fix acceptance criteria.
- `manual-tester` must hand reproducible defects to `issue-investigator` with environment, build
  SHA, expected vs actual behavior, steps, and evidence.
- `test-automation-engineer` must consume stable manual or reproduction scenarios and should not
  automate unclear, subjective, or unstable behavior.

## Nested Support Skills

`issue-investigator` and `code-reviewer` are nested under `software-engineer` for now because they
serve the engineering loop: evidence first, implementation second, review before completion. They
also share the same evidence-pack and definition-of-done artifacts with the engineering workflow.

They might become top-level skills later if real usage shows they are commonly invoked
independently, need separate installation/versioning, or support non-engineering workflows without
depending on the software-engineer evidence loop. Until then, keeping them nested makes the current
collaboration model explicit without adding top-level role sprawl.
