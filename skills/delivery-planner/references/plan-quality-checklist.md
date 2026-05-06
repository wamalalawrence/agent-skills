# Plan-Quality Checklist

The single self-validation pass `delivery-planner` runs in step 6 of its
workflow before emitting the plan. Apply once. Items that fail must be fixed
in this pass or moved to `Open Questions Or Missing Evidence` with a one-line
gap statement.

This loop is bounded by
[docs/review-loops.md](../../../docs/review-loops.md#universal-loop-bounds):
one revision round, no recursion, depth cap of two skills. **Do not run the
checklist a second time on the same plan.** Surface remaining issues to the
user; do not grind.

## Destination

- [ ] The outcome statement is one or two plain-language sentences. No
      vendor names, fashion words, or metaphors.
- [ ] Each success signal names what observes it (manual check, automated
      test, log filter, dashboard widget, metric query). A signal nobody can
      check is not a signal.
- [ ] `Non-goals` is populated. Empty non-goals indicate the planner has
      not actually scoped the work; write `none — bounded by success signals`
      only when that is literally true.
- [ ] Each load-bearing assumption has a one-line *what would change my
      mind* falsifier.
- [ ] Constraints (deadline, compliance, downtime, freeze, dependent teams,
      access) are concrete. "Soon" / "secure" / "scalable" are not
      constraints.
- [ ] Stakeholders are named (role, not just team) for: scope changes,
      phase reviews, destructive-action approvals.

## Phases

- [ ] Each phase fits in ≤ ~150 lines of Markdown when written out. Anything
      larger is re-decomposed in step 4 of the workflow.
- [ ] Each phase names exactly one `recommended_owner` skill. A phase with
      two joint owners is two phases.
- [ ] Each phase marked `ready` has a `recommended_owner` whose `SKILL.md`
      resolves from the canonical skill source. If the skill cannot be
      loaded, the phase is `blocked` and the missing source is surfaced.
- [ ] Each phase has all of: intent (one sentence), prerequisites, inputs,
      scope (in / out), expected outputs, validation, risks, size,
      parallel-safe flag, rollback / abort behavior.
- [ ] No phase intent contains the word "and" without a justified reason.
      "Add the schema migration **and** the read path" is two phases.
- [ ] Each phase's validation is observable. "Tests pass", "PR merged",
      "review signs off", "metric Y holds in staging for 24 h" are
      observable. "Looks right", "feels good", "is clean" are not.
- [ ] Discovery / spike phases are explicitly time-boxed. An open-ended
      "investigate further" phase is a planning failure.
- [ ] No phase requires the executor to perform a forbidden destructive
      action under the
      [destructive-action safety policy](../../../docs/destructive-action-safety.md).
      Such steps are operator runbooks for a human, not agent phases.
- [ ] For code-delivery plans, the last executable path reaches reviewable
      completion: `code-reviewer` outer-loop convergence, Definition-of-Done,
      pushed remote branch, and PR URL, or an explicit blocker. A final phase
      that only validates behavior is incomplete.

## Sequencing

- [ ] The dependency graph in the index matches the prerequisites listed
      on individual phase files. Where they disagree, the per-phase file
      wins and the index is regenerated.
- [ ] The first phase retires the highest-risk question, not the easiest
      task. Easy-first is comfort, not strategy.
- [ ] Parallel-safe phases are flagged correctly. A phase that touches the
      same files as another phase is not parallel-safe regardless of the
      flag.
- [ ] Provisional phases (downstream of a discovery spike with `medium`
      understanding-confidence) are clearly marked `provisional` and never
      flagged as the dispatch pointer.
- [ ] `current_dispatch_pointer` matches the readiness decision per the
      [plan-index template's dispatch-pointer rules](../references/plan-index-template.md#body-sections):
      `READY_FOR_DISPATCH` and `READY_FOR_DISCOVERY` MUST name a phase id
      (the discovery phase, when readiness is `READY_FOR_DISCOVERY`);
      `null` is reserved for `NEEDS_CLARIFICATION` / `NEEDS_EVIDENCE` /
      `BLOCKED`.

## Cross-skill compatibility

- [ ] The phase artifacts live under
      `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/`
      next to `evidence-pack.yml`, not in a parallel directory tree.
- [ ] Phases that depend on the existing
      [evidence pack](../../software-engineer/references/evidence-pack.md)
      reference its fields by path (`investigation.root_cause_status`,
      `acceptance_criteria`, `plan.smallest_change`, `repro_recipe.status`)
      rather than copying the values inline. Copies go stale; pointers do
      not.
- [ ] Phases owned by `software-engineer` for a bug fix reference the
      `repro-recipe.yml` and the failing-regression-test commit when the
      [reproduce-before-fix gate](../../software-engineer/SKILL.md#15-reproduce-before-fix-gate-bug-fixes-only)
      applies.

## Output discipline

- [ ] No empty section headings in the user-facing summary. If
      `Provisional Phases` is empty, the heading is dropped.
- [ ] Phases in the user-facing summary are bullets, not paragraphs.
- [ ] No template echo, no banners, no `Status: ✅` decorations. See
      [Output Discipline](../../../docs/output-discipline.md).
