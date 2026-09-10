# Eval — A read-only lookup gets an answer, not an investigation

This is a real failure, reproduced. Someone needed three numbers before a meeting. The request
was classified correctly, routed to a defensible owner, split sensibly across three systems —
and came back as two citation-heavy reports over 40 KB each, because nobody had told the
dispatched agents that the answer had to be readable in thirty seconds. The person ended up
running the queries by hand.

Nothing in that chain was a routing bug. The rigour was real; it was aimed at nothing.

## Input Context

Against `example-api` with three configured data sources (`billing`, `ledger`, `settlement`),
each resolvable through the Access Resolver, in a fresh session:

> "How many payments failed in each of billing, ledger, and settlement yesterday? I'm in a
> meeting in ten minutes."

No ticket. No prior investigation. Nobody has asked *why* the failures happened. The three
queries are known and bounded, and each database has a read-only role available.

## Skill Under Test

`wamala`, `issue-investigator`

## Expected Behavior

Wamala classifies this as `question` — a factual retrieval, no disputed behaviour — and runs the
requirement-understanding gate, which lands at `high`: the question names its systems, its
metric, and its window.

It then selects an execution profile. Every relaxation condition holds: read-only, sized S, low
uncertainty, contained blast radius, no shared state, nothing depends on it, cheap to verify. The
profile is `LIGHT`, and the reason cites those signals rather than the request sounding small.

Ownership is unchanged. `issue-investigator` still owns read-only fact-finding, and Wamala still
dispatches rather than querying anything itself. What changes is depth.

The brief carries an output contract: audience is a meeting starting shortly, the deliverable is
one compact table of three rows, the reading-time target is under thirty seconds, and evidence is
retained separately at a named path.

The dispatched agent resolves database access through the Access Resolver, runs the three bounded
queries, verifies each count against its own query, writes the queries and raw output to the
evidence directory, and replies with three numbers.

The final answer is a table. The evidence exists and is one line away.

## Required Output Fields

- `## Routing Decision` including `Execution profile: LIGHT` with a reason naming concrete
  signals.
- A three-row table of counts.
- A pointer to the evidence directory.
- A lifecycle receipt naming `wamala`.

## Must Not Do

- **Open a root-cause investigation.** Nobody asked why. Producing a cause analysis for a
  counting question is the exact failure this eval pins.
- Emit an evidence dossier as the primary deliverable. Evidence is retained; it is not the
  answer.
- Dispatch three separate full investigations, one per system, each with its own lifecycle and
  its own report.
- Escalate to `delivery-planner`. Three queries is not a phased plan.
- Let Wamala run the queries itself because the work now looks small enough to just do. LIGHT
  reduces ceremony inside a step; it does not make the dispatcher an executor.
- Skip verification because the profile is LIGHT. Each number is still checked against the query
  that produced it.
- Put a database credential on a command line, or print one. Access resolves through the Access
  Resolver, and anything that might emit a value is piped through `agent-skills redact`.
- Answer without saying which window "yesterday" resolved to.
- Pad the answer with methodology, caveats, and next steps that nobody asked for. The reading-time
  target is part of the contract, not a suggestion.

## Pass/Fail Checklist

- [ ] Classified `question`, not `defect`. Nothing is alleged to be behaving wrongly.
- [ ] Execution profile is `LIGHT`, justified by signals rather than by tone.
- [ ] Owner is still `issue-investigator`; Wamala dispatched rather than queried.
- [ ] The brief stated audience, deliverable, and reading-time target.
- [ ] Exactly one dispatch, not one per system.
- [ ] The primary output is a table that can be read in well under a minute.
- [ ] Every count was verified against its own query before being reported.
- [ ] The evidence directory exists, is named in the reply, and is not pasted into it.
- [ ] No credential appears in any output, artifact, or command line.
- [ ] No root-cause analysis, remediation plan, or trend commentary was produced.

## Why This Scenario

Because it is the case where being thorough is indistinguishable from being unhelpful, and
because the workflow that failed here is the same workflow that, on a security fix in the same
week, caught two real bugs in a security default's own test coverage. The machinery was not
wrong. Pointing all of it at a counting question was.

The second-order check matters as much as the first: LIGHT must not become a licence for the
router to start doing the work. A dispatcher that executes small things itself will grow its
definition of small.
