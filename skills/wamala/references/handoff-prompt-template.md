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
- Prior steps completed this run: <skill: outcome, or "none — you are the first step">
- Artifacts already on disk: <paths, or "none yet">

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
- Write your result to the artifact your skill's contract names (the evidence
  pack, the refinement output, the test plan, the PR URL). A chat-only summary is
  NOT a result: Wamala verifies from disk and will treat a missing artifact as
  an incomplete step.

Scope boundary: <the one thing this step must produce>
Explicitly NOT this step: <the next owner's work, named>

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
- Prior steps completed this run: issue-investigator: root cause confirmed
- Artifacts already on disk: .cache/agent-skills/ABC-123/evidence-pack.yml,
  .cache/agent-skills/ABC-123/repro-recipe.yml

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
