# test-automation-engineer

The full test-automation engineering job: new coverage, maintaining existing suites through
product change, triaging CI failures, diagnosing flakes, deciding what to automate at all, and
keeping the suite explainable.

See [SKILL.md](./SKILL.md) for the full workflow.

## What it does

- Classifies the request into an operating mode — new automation, suite maintenance, failure
  triage, flake investigation, strategy, backlog, coverage gaps, CI integration, or framework
  evolution — and runs the workflow that mode needs.
- Discovers the repository's own automation stack before touching code, and follows it. Framework
  aware, framework independent.
- Classifies failures as product defects, automation defects, expected product changes, flakes,
  data, environment, dependency, or configuration problems — and routes each to its owner.
- Repairs broken suites without weakening the coverage they provided.
- Diagnoses flakiness to a cause rather than retrying it away.
- Decides what to automate now, later, keep manual, move to a lower level, refactor, or remove.
- Preserves requirement → scenario → automated check → CI evidence traceability.
- Collaborates with [`software-engineer`](../software-engineer/),
  [`manual-tester`](../manual-tester/), [`product-owner`](../product-owner/), and
  [`issue-investigator`](../software-engineer/skills/issue-investigator/).

## Reference files

- [framework-discovery.md](./references/framework-discovery.md)
- [failure-triage.md](./references/failure-triage.md)
- [suite-maintenance.md](./references/suite-maintenance.md)
- [automation-backlog.md](./references/automation-backlog.md)
