# Routing Table

The full condition-to-owner mapping `tech-lead` applies, with the reasoning behind each row.
The abbreviated version lives in the skill itself; this file is where the judgement calls are
written down.

Ownership is defined by [skill boundaries](../../../docs/skill-boundaries.md). This table
implements those rules — when the two disagree, skill boundaries wins and this file is wrong.

## Order matters

Rows are evaluated top to bottom, first match wins. The ordering encodes two priorities:

1. **Size before class.** Oversized work is decomposed before anyone asks what kind of work it
   is, because every other route assumes one focused session.
2. **Confidence before class.** A request with unclear intent routes for clarification even when
   its class looks obvious. This is the rule that prevents the most expensive failure in the
   whole system: a confident implementation of a misunderstood requirement.

| Row | Condition | Owner | Reason |
| --- | --- | --- | --- |
| 1 | Spans more than one focused session, several PRs, or several surfaces | `delivery-planner` | Decompose first; every other route assumes one session |
| 2 | A phased plan already exists on disk | `delivery-runner` | The plan's own dispatcher; re-planning is planner-only |
| 3 | Confidence `unknown`/`low`, product intent missing | `product-owner` | Intent is never invented |
| 4 | Confidence `unknown`/`low`, expected vs actual or cause missing | `issue-investigator` | Root cause precedes any fix |
| 5 | `defect`, root cause not established | `issue-investigator` | Evidence and reproduction before a fix |
| 6 | `defect`, root cause established and reproducible | `software-engineer` | Owns the fix and its failing regression test |
| 7 | `change`, intent and acceptance clear | `software-engineer` | Owns implementation and its review gates |
| 8 | `intent-unclear` | `product-owner` | Owns scope, value, acceptance criteria |
| 9 | `question` about behaviour, cause, or history | `issue-investigator` | Read-only by construction |
| 10 | `question` about product intent or priority | `product-owner` | Owns the answer |
| 11 | `review` of an existing diff, branch, or PR | `code-reviewer` | Owns severity and the verdict |
| 12 | `validation`, scenario not yet stable | `manual-tester` | Owns exploratory and manual scope |
| 13 | `validation`, scenario stable and worth automating | `test-automation-engineer` | Owns level choice and fixtures |
| 14 | A term is contested, or a hard-to-reverse decision needs recording | `domain-modeler` | Owns the glossary and ADRs |

## Chains

Most real requests are one step. These are the sequences worth driving automatically, and each
step is re-gated before the next is dispatched.

| Request shape | Chain | Gate between steps |
| --- | --- | --- |
| Feature, scope not yet agreed | `product-owner` → `software-engineer` → `manual-tester` | Refinement must reach `medium`+ confidence and carry acceptance criteria |
| Reported defect | `issue-investigator` → `software-engineer` | Root-cause status must be `confirmed`, or `suspected` with a discriminating experiment |
| Defect worth pinning | `issue-investigator` → `software-engineer` → `test-automation-engineer` | The scenario must be deterministic before automation |
| Manual defect found during testing | `manual-tester` → `issue-investigator` | The defect must carry environment, build SHA, expected vs actual, steps, evidence |
| Oversized anything | `delivery-planner` → `delivery-runner` | Readiness must be `READY_FOR_DISPATCH` |

A chain stops the moment a step returns `blocked` or `needs-context`. Chains are convenience,
not entitlement: the next step is dispatched because its inputs are ready, never because the
table says it comes next.

## Ambiguous cases

The rows above cover the clear requests. These are the ones where the classification is the
actual work, and getting them wrong is the most common routing mistake.

**"It's slow."** Not a defect until expected behaviour exists. Without a target — a budget, an
SLA, a previous measurement — this is `intent-unclear` and goes to `product-owner`. With a
target and a regression, it is a defect and goes to `issue-investigator`.

**"Add a config flag so we can turn X off."** Reads like `change`, often is not. If the reason
for the flag is an unresolved defect, the flag is a workaround and the defect is the work.
Route to `issue-investigator` and say why.

**"Refactor this module."** `change` when the target state is described. `intent-unclear` when
the reason is "it's messy" — refactors without a stated goal have no acceptance criteria and no
way to end.

**"Why did this break?"** `question` → `issue-investigator`. It stays a question until someone
asks for a fix. Do not route to `software-engineer` on the assumption a fix is wanted; that
decision belongs to the person who asked.

**"Review this and fix what you find."** Two owners. Dispatch `code-reviewer` first, return the
findings, and let the user decide on the fix. Bundling them means the reviewer's independence is
lost — the same context both writes and judges the change.

**"The test is flaky."** `validation` → `test-automation-engineer`, which owns flakiness risk.
It becomes `defect` → `issue-investigator` only when the flake turns out to be a real race in
production code rather than in the test.

**A bare ticket key with nothing else.** Do not classify from the key. Fetch the ticket if the
capability report says a tracker resolves; if it does not, ask the user for the summary and
acceptance criteria. Guessing intent from a key or a branch name is a documented failure mode.

**A request that is really two requests.** Split it, route the first, and say plainly that the
second is waiting. Do not average two requests into one destination.

## Routes that do not exist

Worth stating, because each is a plausible-looking mistake:

- **Never route to `code-reviewer` inside an implementation step.** The engineer runs that loop
  itself. A lead that also dispatches the reviewer creates two review loops and breaks the
  depth cap.
- **Never route to `delivery-planner` mid-chain.** If a step turns out to be oversized, the step
  stops and surfaces; the planner re-decomposes on its own next run.
- **Never route to `tech-lead`.** No skill invokes itself, directly or transitively.
- **Never route around a blocker.** A blocked step means stop, not "try a different skill".

## Recording what the routing got wrong

A misclassified request shape is a durable lesson about this project, which is exactly what the
[repo knowledge base](../../../docs/repo-knowledge.md) is for:

```bash
python3 scripts/knowledge.py lesson add \
  --id perf-requests-need-a-target \
  --trigger "when a request says something is slow" \
  --action "ask for the target or SLA first; without one there is no defect to investigate" \
  --domain process
```

Over time these accumulate into routing that fits the project rather than the generic table.
