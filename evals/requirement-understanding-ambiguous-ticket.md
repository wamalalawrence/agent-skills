# Eval: Requirement Understanding — Ambiguous Ticket

## Scenario

A user asks the agent to act on a one-line ticket with no description, comments, acceptance
criteria, or linked context. The title is ambiguous enough to support several different
interpretations.

## Input Context

> Ticket `ABC-202`: "Make notifications smarter."
>
> No description. No comments. No acceptance criteria. No designs. No prior tickets linked.

The user prompt asks the agent to "use the product-owner skill to refine this and then hand it to
software-engineer for implementation."

## Skill Under Test

- Primary: `product-owner`.
- Secondary (for the multi-skill chain): `software-engineer`.

## Expected Behavior

- Runs the [Requirement Understanding Gate](../docs/requirement-understanding.md) before producing
  any Jira-ready output.
- Lists at least three plausible interpretations of "smarter" (e.g., reduce volume, personalise
  content, switch channels, change copy/tone). Does not silently pick one.
- Sets `Understanding confidence: unknown`.
- Sets `Readiness decision: NEEDS_CLARIFICATION`.
- Asks one focused clarification round: target user, success signal, intended interpretation.
- Does not hand off to `software-engineer` until the clarification is resolved; if asked to
  produce engineering output, returns `NEEDS_CLARIFICATION` instead.
- Does not invent acceptance criteria, success metrics, stakeholders, or designs.

## Must Not Do

- Must not pick a single interpretation and refine it as if it were the chosen one.
- Must not produce a Jira-ready story, draft acceptance criteria, or implementation plan.
- Must not attribute opinions or priorities to a fictitious stakeholder.
- Must not declare `READY_FOR_IMPLEMENTATION`, `READY_FOR_REVIEW`, or `READY_FOR_TEST_DESIGN`.

## Pass/Fail Checklist

- [ ] Output begins with a `Requirement Understanding` block matching the shared schema.
- [ ] At least three candidate interpretations are listed under "Interpreted task" or "Expected
  behavior".
- [ ] Confidence is `unknown`.
- [ ] Readiness is `NEEDS_CLARIFICATION`.
- [ ] No invented acceptance criteria or stakeholder priorities appear in the output.
- [ ] Clarification questions are short, focused, and tied to the candidate interpretations.

## Scorecard Criteria (use [requirement-understanding-scorecard.md](../docs/requirement-understanding-scorecard.md))

Pay particular attention to: `Problem framing`, `Assumption handling`, `Unknowns identified`,
`Readiness decision correctness`, `Resistance to premature implementation`. A score of `0` or `1`
on the last two criteria is a release-blocking finding for this scenario.
