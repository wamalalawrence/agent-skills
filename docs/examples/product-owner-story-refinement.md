# Product Owner Story Refinement Example

## Input Prompt

```text
Use the product-owner skill.

Request: allow users to save frequently used report filters.
Users: analysts who run the same reports every week.
Known context: current filters must be rebuilt manually each visit; no design is available yet.
```

## Assumed Available Context

- Rough product request and target user.
- Current workflow summary.
- Known constraints or missing design decisions.
- No private roadmap or stakeholder priorities unless supplied.

## Expected Skill Behavior

- Clarify the product goal, user value, and problem statement.
- Define in scope, out of scope, assumptions, dependencies, UX notes, and non-functional needs.
- Ask or record open questions instead of inventing missing product decisions.
- Produce Jira-ready story/task structure with testable acceptance criteria.
- Hand off feasibility, manual testing, and automation notes without prescribing implementation.

## Sample Output Structure

```markdown
## Product Summary

- Product goal: let analysts save and reuse report filter sets.
- User/stakeholder value: reduce repeated setup work for recurring reports.
- Problem statement: analysts rebuild the same filters manually, which costs time and increases error risk.

## Scope

- In scope: create, name, apply, rename, and delete saved filters for the current user.
- Out of scope: sharing saved filters across users.
- Assumptions: saved filters are user-specific unless stakeholders say otherwise.
- Dependencies: UX decision for where saved filters appear.
- UX notes: empty state, duplicate names, and rename/delete confirmation need decisions.
- Non-functional requirements: saved filters must not expose another user's private report context.
- Open questions: ...

## Jira-Ready Story/Task Format

- Title: Save and reuse report filters
- Type: Story
- Description: ...

## Acceptance Criteria

- [ ] Given an analyst has selected filters, when they save the filter set with a valid name, then it appears in their saved filters list.
- [ ] Given another user signs in, the first user's saved filters must not be visible.
```

## What The Skill Should Avoid

- Inventing a design, permission model, or deadline.
- Treating an unclear bug complaint as a feature story without investigation.
- Writing acceptance criteria such as "works as expected".
- Prescribing database schema or test framework details.
