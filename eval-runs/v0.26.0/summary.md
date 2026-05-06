# v0.26.0 Eval Run Summary

Focus: dispatch correctness, Jira scope isolation, existing PR detection, and conclusive
code-delivery completion.

## Scenarios Reviewed

- [`skill-source-resolution-ambiguity`](../../evals/skill-source-resolution-ambiguity.md):
  added the explicit user-supplied skill path variant. Expected behavior now blocks agents from
  checking only `.skills/...` when the prompt names another skill source.
- [`delivery-planner-phased-plan`](../../evals/delivery-planner-phased-plan.md): added checks that
  ready phases must resolve their `recommended_owner` skill and code-delivery plans cannot end with
  validation alone.
- [`jira-issue-scope-and-existing-pr`](../../evals/jira-issue-scope-and-existing-pr.md): new eval
  requiring one Jira task per branch/PR and an open-PR/remote-branch scan before new implementation.

## Result

Repository validation passes when these updated contracts are present in the skill files, evidence
pack reference, planner templates, and evals. Remaining risk is host compliance: agents still need
to actually follow the source-resolution and dispatch contracts at runtime.
