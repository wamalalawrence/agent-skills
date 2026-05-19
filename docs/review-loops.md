# Skill Review Loops (Bounded)

`agent-skills` is built around the idea that specialised skills produce **better** output when
their work is reviewed by a peer skill before being declared done — the same way teams pair
implementers with reviewers, requirements with testers, and tests with code review. This
document defines how those loops are wired across the repo and, more importantly, how they
**terminate** so the agent never spins forever.

> **TL;DR.** Every cross-skill review loop in this repo is **bounded to one revision round** by
> default. The producing skill proposes, the reviewer skill validates, the producer revises
> at most once, and then the artifact ships with any remaining issues recorded as
> `Open Questions` / `Follow-ups` rather than triggering another round.

## Why this exists

Without explicit bounds, two failure modes are common in multi-skill agents:

1. **Endless ping-pong.** Reviewer asks a question, producer answers, reviewer asks the next
   question, producer answers — neither has authority to stop, so the loop only ends when
   the context window does.
2. **Silent degradation.** Producer hands work off, reviewer raises blockers, producer fixes
   one blocker, reviewer never re-checks because the contract did not require it. The
   "review" was decorative.

Both are avoided by the same rule: **each loop has a producer, one reviewer pass, one revision
window, and a written "ship with follow-ups" exit.**

## Wired loops

Each entry: producer → reviewer (mode), trigger, exit rule.

- **`software-engineer` → `code-reviewer` (`inner`).** Trigger: after Phase 2
  Implementation, before validation runs. Exit: engineer fixes `blocker` / `major`
  findings and reruns the reviewer within `${CODE_REVIEWER_MAX_ROUNDS}` (default `3`)
  with strictly-decreasing `blocker`+`major` count per round. Remaining `minor` items
  become PR review notes.
- **`software-engineer` → `code-reviewer` (`outer`).** Trigger: after Phase 3
  Validation, before PR/commit. Exit: engineer fixes `blocker` findings and reruns
  the reviewer within `${CODE_REVIEWER_MAX_ROUNDS}` (default `3`) with
  strictly-decreasing finding counts. Surviving `major` / `minor` ship as PR notes.
- **`issue-investigator` → self-validation against the
  [investigation-quality checklist](#investigation-quality-checklist).** Trigger: before
  emitting the final `Investigation Result`. Exit: one revision pass; items not closed
  by revision must appear in `Open Questions Or Missing Evidence`.
- **`product-owner` → `manual-tester` (testability quick-check) + self-check against
  the [Definition of Ready](../skills/product-owner/SKILL.md#definition-of-ready-gate-before-handoff).**
  Trigger: before emitting the tracker-ready output. Exit: one revision round; unresolved
  items make the work item a `Spike` / `Discovery`, not fix-ready.
- **`manual-tester` → self-check against the
  [test-plan review checklist](#test-plan-review-checklist); `issue-investigator` for
  reproducible defects.** Trigger: before emitting `Execution Result` and any
  `Defects Found`. Exit: one revision round on the plan; defects that fail the
  investigator handoff become `product question` instead of `defect`.
- **`test-automation-engineer` → `code-reviewer` (`manual` mode, `test-quality`
  profile).** Trigger: after step 6 "Review automation value", before merging the new
  tests. Exit: one revision round on the new test files; surviving findings ship as
  inline TODOs with linked follow-up issues.
- **`delivery-planner` → self-validation against the
  [plan-quality checklist](../skills/delivery-planner/references/plan-quality-checklist.md).**
  Trigger: before emitting the final `Plan Summary`. Exit: one revision round on the
  destination + phase files; surviving items move to `Open Questions Or Missing
  Evidence` with a one-line gap statement. The planner does **not** invoke any other
  skill — phase dispatch is the executor's job — so this loop introduces no new
  cross-skill recursion and respects the depth cap of two skills.

## Universal loop bounds

These rules apply to **every** cross-skill review in this repo and override anything more
permissive in individual SKILL.md files:

1. **One revision round per loop by default.** The producer may revise once after the
   reviewer's first pass. A second reviewer pass only checks that the previously raised
   `blocker` items were addressed; it does not introduce new findings. New issues found in
   the second pass are written as `Follow-up` items, not as a third round.
   - **Exception:** the `software-engineer` ↔ `code-reviewer` inner/outer loops use
     `${CODE_REVIEWER_MAX_ROUNDS}` (default `3`) with a strictly-decreasing
     `blocker`+`major` count per round. The cap and the convergence rule are still
     binding; the loop must stop and surface "not converging" instead of grinding.
2. **The reviewer never edits the producer's artifact.** It returns findings; the producer
   decides how to apply them.
3. **`blocker` findings stop the loop.** A producer that cannot resolve a `blocker` after
   one revision must hand off to the human (or a different skill) instead of trying again.
4. **No skill invokes itself, directly or transitively.** `code-reviewer` calling
   `code-reviewer` is forbidden. So is `code-reviewer` → `issue-investigator` →
   `code-reviewer`: a helper skill called by a reviewer must return its result, not
   re-invoke the original reviewer. Helpers that need to refer to reviewer output read
   the persisted evidence pack instead.
5. **Loop depth cap of two skills.** A producer may invoke at most one reviewer; that
   reviewer may invoke at most one helper skill (e.g. `code-reviewer` may call
   `issue-investigator` for missing context). The helper returns context only — it
   does not start a new review loop and does not re-invoke any skill already on the
   call chain.
6. **Persistent artifacts, not chat.** Cross-skill handoffs use the
   [evidence-pack and DoD files](../skills/software-engineer/references/evidence-pack.md) in
   `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}`. Re-reading
   that file is cheaper, in tokens and reliability, than re-deriving context in chat.

## Investigation-quality checklist

Used by `issue-investigator` as its single self-validation pass before emitting the result.
Apply once; items left unchecked move to `Open Questions Or Missing Evidence`.

- [ ] Issue type classification is supported by at least one cited piece of evidence.
- [ ] Expected behavior is sourced from a real artifact (ticket, AC, doc, test) — not invented.
- [ ] Root-cause status (`unknown` / `suspected` / `confirmed` / `disproved`) matches the
      [evidence gate](../skills/software-engineer/skills/issue-investigator/SKILL.md#5-establish-root-cause-status-and-confidence)
      for the recommended next action.
- [ ] At least two of the [three hypotheses](../skills/software-engineer/skills/issue-investigator/SKILL.md#three-hypothesis-discipline)
      were considered; the discriminating experiment is recorded.
- [ ] No `safe check` is mutating, unbounded, or requires a credential the user has not
      configured.
- [ ] No discovered credential, token, or secret value is echoed in the output.
- [ ] Recommendation respects the lower of root-cause confidence and requirement-understanding
      confidence.

## Test-plan review checklist

Used by `manual-tester` as its single self-validation pass before emitting the plan.

- [ ] Each acceptance criterion is covered by at least one scenario, or is explicitly listed
      as out of scope for this round.
- [ ] At least one negative scenario per user-facing AC.
- [ ] Environment, build / commit SHA, role, and test data are stated or marked unknown.
- [ ] Defects separate `functional defect`, `usability observation`, `environment issue`, and
      `product question`.
- [ ] No scenario relies on production data, real customer PII, or real secrets.
- [ ] Reproducible defects carry the smallest set of facts the
      [`issue-investigator`](../skills/software-engineer/skills/issue-investigator/SKILL.md)
      handoff needs.

## When to skip a loop

- **Trivial output.** A one-line answer (`"yes that's a bug"`, `"the tracker config is missing
  JIRA_HOST"`) does not need a review loop. Reserve loops for artifacts that downstream
  skills or humans will act on.
- **Read-only or advisory output.** A `safe checks the user can run` block, a `feasibility
  note`, or an `automation candidates` list does not require a second reviewer when the
  producer already cites evidence.
- **The user explicitly skipped it.** A prompt of "skip review" or "draft only" disables
  the loop. Note this in the output so downstream skills do not assume the artifact was
  validated.

## Anti-patterns

- Producer asks reviewer; reviewer asks producer to "expand"; producer expands; reviewer
  asks for more — **stop after one revision**.
- Reviewer rewrites the producer's artifact in-place — **return findings, do not edit**.
- Producer calls reviewer in a loop until verdict is `PASS` — **a `PASS_WITH_NOTES` after
  one revision is the exit condition**.
- Reviewer invokes a third skill which invokes a fourth — **depth cap is two**.
