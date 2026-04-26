# Product Owner Eval: Story Refinement

## Input Context

A stakeholder says, "Let users export their activity history." No target user, export format,
permissions, retention limits, privacy constraints, or success measure is provided.

## Skill Under Test

`product-owner`

## Expected Behavior

- Clarifies goal, users, value, scope, and unknowns before producing implementation-ready work.
- Produces either focused clarification questions or a clearly labeled draft with assumptions.
- Includes observable acceptance criteria only when enough facts are available.
- Calls out privacy, permissions, data range, empty states, and error handling as areas to resolve.
- Hands technical feasibility and testability concerns to related skills when appropriate.

## Required Output Fields

- Product summary.
- Scope.
- Jira-ready story/task format, if ready.
- Acceptance criteria, if justified.
- Edge cases.
- Handoff notes.

## Must Not Do

- Must not invent export format, legal requirements, retention rules, or stakeholder approval.
- Must not produce a final Jira-ready story if core product facts are missing.
- Must not prescribe architecture or database design.
- Must not omit negative acceptance criteria when a final story is produced.

## Pass/Fail Checklist

- [ ] Missing product facts are surfaced.
- [ ] Acceptance criteria are testable or deferred until clarified.
- [ ] Scope and out-of-scope are explicit.
- [ ] Handoffs to engineering/testing are appropriate.
- [ ] Output avoids invented business context.