# Handoff-Prompt Template

The binding shape of the brief `wamala` hands to each **fresh, empty-context** agent when it
dispatches a step. The receiving agent has no conversation history, so this brief has to carry
everything it needs — and nothing it does not.

Fill every `<...>` placeholder. Use repo-relative paths. Pass pointers, not file contents: the
whole reason for a fresh agent is that it reads only what its step needs.

## Template

```text
You are starting a fresh task with empty context. Do exactly ONE step of a larger
piece of work, then stop and report.

Request (as the user stated it): <verbatim request, or a faithful one-line summary>
Work key: <work-key>
Task cache dir: <cache-dir>/<work-key>/

What has already been established (do not re-derive this):
- Classification: <class> — <one-line reason>
- Requirement-understanding confidence: <unknown|low|medium|high>
- Execution profile: <LIGHT|STANDARD|RIGOROUS> — <one-line reason>
- Prior steps completed this run: <skill: outcome, or "none — you are the first step">
- Artifacts already on disk: <paths, or "none yet">

What the human actually needs back:
- Audience: <who reads this>
- Primary question: <the one question they are asking>
- Deliverable: <table | short answer | patch | test plan | report>
- Reading-time target: <e.g. under 30 seconds>
- Evidence: <cited-inline | retained-separately at <path> | none>

Owner skill (BINDING): load and follow
<skill-source>/<owner>/SKILL.md from the canonical skill source. This step's owner is
"<owner>". If that SKILL.md cannot be loaded, or its `name:` field does not equal
"<owner>", stop with "BLOCKED: owner skill unavailable" and list the paths you
checked. Do not substitute a different skill and do not fall back to a generic
workflow.

Do this:
- Run that skill's full workflow for THIS step only, including its own PREFLIGHT
  start-task.sh and closing finish-task.sh lifecycle wrappers.
- Stay inside your step's ownership. If the work turns out to belong to another
  skill, stop and say which one — do not do it yourself.
- Match the workflow depth to the execution profile above. At LIGHT: answer the
  question directly, verify the answer, keep evidence but do not build a dossier.
  At RIGOROUS: full evidence and review discipline, unchanged.
- Meet the output contract above. The deliverable and the evidence are NOT the
  same artifact: write the evidence where the contract says, and keep the primary
  answer to the size and reading time asked for.
- Write progress as you go, not only at the end:
  `agent-skills blackboard progress <work-key> --by <owner> --kind <kind> --note "..."`
  after each meaningful milestone. A run that is interrupted must leave behind
  what it had already learned; one that writes nothing for an hour is
  indistinguishable from one that is stuck.
- Budget your time. If you are materially past <expected-effort> without a
  milestone landing, narrow the scope to the next single checkable thing and say
  what you dropped, rather than continuing to spend.
- Write your result to the artifact your skill's contract names (the evidence
  pack, the refinement output, the test plan, the PR URL). A chat-only summary is
  NOT a result: Wamala verifies from disk and will treat a missing artifact as
  an incomplete step.
- Never print a credential. Pipe any command that might emit one through
  `agent-skills redact`, and resolve service access through the Access Resolver.

Scope boundary: <the one thing this step must produce>
Explicitly NOT this step: <the next owner's work, named>
Expected effort: <minutes> — a budget for reassessment, not a deadline

Stop and report blocked (do not improvise) if: the owner skill is unavailable,
required context is missing, the requirement-understanding gate ends at `unknown`
or `low`, validation fails, or the step would require a forbidden destructive
action, a discovered credential, or a production mutation.

Final message MUST state: the owner skill you ran, the outcome
(done | blocked | needs-context), the artifact path you wrote, and — if you
stopped — the specific missing thing and who should supply it.
```

## Filling rules

- `<owner>` comes from the [routing table](./routing-table.md). Exactly one owner per handoff.
  A brief naming two skills is a bug: the second owner loses the independent context that made
  dispatching worthwhile.
- `<skill-source>` is resolved per
  [skill-source resolution](../../../docs/skill-source-resolution.md), honouring any explicit
  path the user supplied.
- `<class>` and the confidence verdict are copied from Wamala's own step 1 and step 2. Passing
  them forward is what stops the fresh agent re-running the gate from scratch.
- **`Prior steps completed this run`** is one line per step, never a transcript. If the
  refinement produced acceptance criteria, point at the file; do not paste them.
- **`Explicitly NOT this step`** matters more than it looks. Without it, a `software-engineer`
  agent handed a fixed defect will often keep going and write the regression automation too,
  which silently removes the `test-automation-engineer` step's independent judgement about test
  level and stability.
- **`Execution profile`** comes from `agent-skills execution-profile`, not from a feeling about
  how big the work looks. See [adaptive execution](../../../docs/adaptive-execution.md). The
  profile changes how much ceremony the step runs, never who owns it and never the safety floor.
- **The output contract** is the fix for a real failure: a request for three read-only numbers
  came back as two citation-heavy reports over 40 KB each, because the dispatched skill builds
  evidence trails by default and nobody had told it the answer needed to be readable in a
  meeting. State the audience and the reading-time target and that does not happen.
- **`Expected effort`** exists so the agent can reassess itself, and so
  `agent-skills watchdog` has something to measure. An overscoped brief once ran about an hour
  and wrote nothing at all; incremental progress writes and a stated budget are what make that
  visible while it is still happening.
- When the user asked to approve each handoff, print the filled brief and pause instead of
  dispatching.

## Worked example

Second step of a defect chain. `issue-investigator` has confirmed the root cause; the fix is
next.

```text
You are starting a fresh task with empty context. Do exactly ONE step of a larger
piece of work, then stop and report.

Request (as the user stated it): invoice search drops the status filter on page 2
Work key: ABC-123
Task cache dir: .cache/agent-skills/ABC-123/

What has already been established (do not re-derive this):
- Classification: defect — a user-visible behaviour differs from the stated filter contract
- Requirement-understanding confidence: high
- Execution profile: STANDARD — a contained single-service fix, root cause already confirmed
- Prior steps completed this run: issue-investigator: root cause confirmed
- Artifacts already on disk: .cache/agent-skills/ABC-123/evidence-pack.yml,
  .cache/agent-skills/ABC-123/repro-recipe.yml

What the human actually needs back:
- Audience: reviewer
- Primary question: does pagination preserve every active filter?
- Deliverable: patch with a failing-first regression test
- Reading-time target: the PR description under a minute
- Evidence: cited-inline in the PR

Owner skill (BINDING): load and follow
.skills/software-engineer/SKILL.md from the canonical skill source. This step's owner is
"software-engineer". If that SKILL.md cannot be loaded, or its `name:` field does not
equal "software-engineer", stop with "BLOCKED: owner skill unavailable" and list the
paths you checked. Do not substitute a different skill and do not fall back to a
generic workflow.

Do this:
- Run that skill's full workflow for THIS step only, including its own PREFLIGHT
  start-task.sh and closing finish-task.sh lifecycle wrappers.
- Stay inside your step's ownership. If the work turns out to belong to another
  skill, stop and say which one — do not do it yourself.
- Write your result to the artifact your skill's contract names.

Scope boundary: the URL builder carries every active filter across pagination,
with a failing-first regression test committed before the fix
Explicitly NOT this step: regression automation beyond that one test — the
test-automation-engineer step owns level choice and fixture design
Expected effort: 40 minutes — a budget for reassessment, not a deadline

Stop and report blocked (do not improvise) if: the owner skill is unavailable,
required context is missing, the requirement-understanding gate ends at `unknown`
or `low`, validation fails, or the step would require a forbidden destructive
action, a discovered credential, or a production mutation.

Final message MUST state: the owner skill you ran, the outcome
(done | blocked | needs-context), the artifact path you wrote, and — if you
stopped — the specific missing thing and who should supply it.
```

Note what the brief does **not** contain: the investigation's findings, the ticket text, or the
reproduction steps. All three are on disk, and the fresh agent reads them itself. Pasting them
in would rebuild the accumulated context that fresh-context dispatch exists to avoid.

## Worked example — LIGHT

The case this profile exists for. Three read-only numbers for a meeting, previously answered
with two evidence dossiers over 40 KB each.

```text
You are starting a fresh task with empty context. Do exactly ONE step, then stop
and report.

Request (as the user stated it): how many payments failed in each of billing,
ledger, and settlement yesterday?
Work key: local-2026-09-failed-payment-counts
Task cache dir: .cache/agent-skills/local-2026-09-failed-payment-counts/

What has already been established (do not re-derive this):
- Classification: question — a factual retrieval, no behaviour is disputed
- Requirement-understanding confidence: high
- Execution profile: LIGHT — read-only, bounded, three known queries, contained
  blast radius, cheap to verify
- Prior steps completed this run: none — you are the first step
- Artifacts already on disk: none yet

What the human actually needs back:
- Audience: engineering meeting starting shortly
- Primary question: the failed-payment count per system for yesterday
- Deliverable: one compact table, three rows
- Reading-time target: under 30 seconds
- Evidence: retained-separately at
  .cache/agent-skills/local-2026-09-failed-payment-counts/evidence/

Owner skill (BINDING): load and follow
.skills/software-engineer/skills/issue-investigator/SKILL.md. This step's owner is
"issue-investigator". If that SKILL.md cannot be loaded, or its `name:` field does
not equal "issue-investigator", stop with "BLOCKED: owner skill unavailable".

Do this:
- Run the skill's workflow at LIGHT depth: resolve access, run the three bounded
  read-only queries, verify each count against its own query, and answer.
- Do NOT open a root-cause investigation. Nobody has asked why yet.
- Put the queries and raw output in the evidence directory. Put THREE NUMBERS in
  your reply.
- Resolve database access through the Access Resolver. Never put a credential on
  a command line, and pipe anything that might print one through
  `agent-skills redact`.

Scope boundary: one table, three rows, each number verified against its query
Explicitly NOT this step: why the failures happened, any remediation, any trend
analysis. If the numbers prompt a "why", that is a separate request.
Expected effort: 15 minutes — a budget for reassessment, not a deadline

Final message MUST state: the owner skill you ran, the outcome, the evidence
directory path, and the table.
```

The contrast with the example above is the whole point. Same dispatch machinery, same ownership
rules, same safety floor, same verification-from-artifacts — a fraction of the ceremony, because
the question is small and reading a number back is cheap to check.
