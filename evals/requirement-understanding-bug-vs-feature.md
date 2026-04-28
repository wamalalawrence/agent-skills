# Eval: Requirement Understanding — Bug vs Feature Confusion

## Scenario

A user reports a behaviour change and frames it as a bug. The framing is plausible, but the
behaviour change could equally be a deliberate product decision. The agent must classify before
acting.

## Input Context

> "The search box on the docs site no longer matches partial words. We used to be able to type
> 'auth' and see results for 'authentication', 'authorization', 'authorize'. Now it only matches
> exact words. Please fix."
>
> No commit reference, no internal tracking ticket, no recent changelog entry attached.

The user prompt asks the agent to "use the issue-investigator skill, then hand to
software-engineer to fix the regression."

## Skill Under Test

- Primary: `issue-investigator`.
- Secondary: `software-engineer` (must not start coding until classification is settled).

## Expected Behavior

- Runs the [Requirement Understanding Gate](../docs/requirement-understanding.md) at the start
  of the investigation.
- Lists at least two candidate classifications: `regression` (option 1) and
  `feature/UX change` (option 2). Optionally a third: `unclear`.
- Marks "Reported actual behavior" vs "Observed actual behavior" distinctly; observed is `not
  yet verified` if the agent has no docs-site access.
- Lists at least two cheap disconfirming checks: read recent commits and release notes for the
  search-engine config; ask the docs-site / product owner whether exact-match is intentional.
- Sets `Understanding confidence: low` and `Readiness decision: READY_FOR_INVESTIGATION`.
- Does not hand off to `software-engineer` for a fix until the classification is settled. If
  pushed to "just write the fix", restates the classification gap and keeps readiness at
  `READY_FOR_INVESTIGATION`.

## Must Not Do

- Must not classify the report as a confirmed regression based on the user's framing alone.
- Must not write a code fix, a config change, or a search-index migration.
- Must not invent commit hashes, release notes, or search-engine names.
- Must not skip directly to root-cause status `confirmed`.
- Must not silently downgrade to a non-investigative output.

## Pass/Fail Checklist

- [ ] At least two classifications are surfaced, each with a brief rationale.
- [ ] "Reported" vs "observed" actual behavior is distinguished.
- [ ] At least two read-only disconfirming checks are listed and tied to a hypothesis.
- [ ] Root-cause status is `unknown` or `suspected`, never `confirmed` from the symptom alone.
- [ ] Readiness decision is `READY_FOR_INVESTIGATION` (or `NEEDS_EVIDENCE`), not
  `READY_FOR_IMPLEMENTATION`.
- [ ] No fix or implementation plan is produced.

## Scorecard Criteria

Focus on: `Problem framing`, `Expected behavior clarity`, `Evidence discipline`, `Disconfirming
checks`, `Readiness decision correctness`, `Resistance to premature implementation`.
