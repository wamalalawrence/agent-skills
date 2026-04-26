# Manual Tester Test Plan Example

## Input Prompt

```text
Use the manual-tester skill.

Change: users can save report filters.
Acceptance criteria: create, apply, rename, delete, and private visibility for saved filters.
Environment: staging, build 2026.04.20.2, Chrome latest.
Roles/data: analyst account with sample report data.
```

## Assumed Available Context

- Acceptance criteria and expected behavior.
- Environment, build/version/commit, user role, and test data.
- Known changed areas or risk notes from engineering.

## Expected Skill Behavior

- Build a compact manual plan tied to acceptance criteria and risk.
- Include core, negative, edge, permission, and regression scenarios.
- Record execution results separately from the plan.
- Write defects with expected vs actual behavior, evidence, environment, and retest guidance.
- Hand reproducible defects to `issue-investigator` and stable candidates to
  `test-automation-engineer`.

## Sample Output Structure

```markdown
## Manual Test Plan

- Test scope: saved report filters.
- Environment/build/version/commit: staging 2026.04.20.2, commit abc1234.
- Test data and user roles: analyst account with sample report data.
- Risks: permission leakage, stale filters, duplicate names.

## Test Scenarios

- [ ] Save a valid filter set and verify it appears in the saved list.
- [ ] Apply a saved filter set and verify report results update.
- [ ] Attempt to view saved filters from a different user.

## Execution Result

- Passed:
- Failed:
- Blocked:
- Not tested:
- Residual risk:

## Defects Found

### Saved filter visible to another user

- Severity: blocker
- Environment: ...
- Steps to reproduce: ...
- Actual vs expected behavior: ...
- Defect evidence: ...
- Retest guidance: ...
```

## What The Skill Should Avoid

- Calling validation complete without environment/build details.
- Reporting defects without reproducible steps or evidence.
- Treating unclear expected behavior as a failure.
- Automating subjective exploratory observations by default.
