# Routing Table

The full condition-to-owner mapping `wamala` applies, with the reasoning behind each row.
The abbreviated version lives in the skill itself; this file is where the judgement calls are
written down.

Ownership is defined by [skill boundaries](../../../docs/skill-boundaries.md). This table
implements those rules — when the two disagree, skill boundaries wins and this file is wrong.

## Order matters

Rows are evaluated top to bottom, first match wins. The ordering encodes three priorities:

1. **Evidence before everything.** When the request is "make this enormous input readable", no
   other route can proceed — the owner it would dispatch to cannot fit the input either.
2. **Size before class.** Oversized work is decomposed before anyone asks what kind of work it
   is, because every other route assumes one focused session.
3. **Confidence before class.** A request with unclear intent routes for clarification even when
   its class looks obvious. This is the rule that prevents the most expensive failure in the
   whole system: a confident implementation of a misunderstood requirement.

Rows 2 to 4 are about a plan that already exists, and their order is the point. A plan that has
to change goes to the planner before anything tries to run it (row 2). A plan that is fine goes
to whoever can actually walk it: `delivery-runner` when a dispatched agent can open agents of its
own (row 4), and Wamala itself, one phase per dispatch, when it cannot (row 3). Nested dispatch
is decided by [the dispatch-depth probe](./dispatch-topology.md#the-probe), never assumed; an
unproven answer takes row 3, because a runner that cannot dispatch stops before its first phase
and one that was never needed costs nothing.

Row 0 is narrow on purpose. It fires when **reducing the input is the request**, not whenever a
large file is mentioned. A defect report that happens to attach a 200 MB log is still `defect` →
`issue-investigator`; that skill calls the Context Optimizer runtime itself, because dispatching a
second agent purely to shrink a file adds a whole agent's context to save some. See
[the ambiguous case below](#is-this-oversized-input-or-just-a-big-file).

| Row | Condition | Owner | Reason |
| --- | --- | --- | --- |
| 0 | Reducing an input too large to read **is** the request | `context-optimizer` | Owns bounded, traceable extraction; nothing else can start until the evidence fits |
| 1 | Spans more than one focused session, several PRs, or several surfaces | `delivery-planner` | Decompose first; every other route assumes one session |
| 2 | `plan-amendment` — decision-gate answers, a new constraint, or a phase criterion shown unsatisfiable | `delivery-planner` | Only the planner edits a plan |
| 3 | A phased plan exists on disk; nested dispatch unavailable or unproven | each phase's owner, in Wamala plan mode | The runner cannot dispatch from inside a dispatched agent |
| 4 | A phased plan already exists on disk | `delivery-runner` | The plan's own dispatcher; re-planning is planner-only |
| 5 | Confidence `unknown`/`low`, product intent missing | `product-owner` | Intent is never invented |
| 6 | Confidence `unknown`/`low`, expected vs actual or cause missing | `issue-investigator` | Root cause precedes any fix |
| 7 | `defect`, root cause not established | `issue-investigator` | Evidence and reproduction before a fix |
| 8 | `defect`, root cause established and reproducible | `software-engineer` | Owns the fix and its failing regression test |
| 9 | `change`, intent and acceptance clear | `software-engineer` | Owns implementation and its review gates |
| 10 | `intent-unclear` | `product-owner` | Owns scope, value, acceptance criteria |
| 11 | `question` about behaviour, cause, or history | `issue-investigator` | Read-only by construction |
| 12 | `question` about product intent or priority | `product-owner` | Owns the answer |
| 13 | `design-review` of a page, screen, or flow against a stated standard | `manual-tester` | Observed versus expected; usability observations kept apart from defects |
| 14 | `design-review` with no stated standard | `product-owner` | Owns UX intent; findings are refinement input, not edits |
| 15 | An implementation step's review ran in the writer's context; no nested dispatch | `code-reviewer` | Independence needs a fresh context: a sibling step over the committed diff |
| 16 | `review` of an existing diff, branch, or PR | `code-reviewer` | Owns severity and the verdict |
| 17 | `automation`, but the behaviour the test should assert is not agreed | `product-owner` | Automation must not freeze an unsettled assumption into CI |
| 18 | `automation`, but a failing automated test points at a product defect | `issue-investigator` | Product root cause is never the suite's to decide |
| 19 | `automation`, but the scenario is not stable enough to assert mechanically | `manual-tester` | Exploratory scope stays manual |
| 20 | Tests for a code change this session is making or just made | `software-engineer` | Owns the developer tests that ship with its own change |
| 21 | `automation` — new coverage, a broken suite, CI triage, flakes, runtime, or a backlog | `test-automation-engineer` | Owns the suite, its failures, and its level choices |
| 22 | `validation`, scenario not yet stable | `manual-tester` | Owns exploratory and manual scope |
| 23 | `validation`, scenario stable and worth automating | `test-automation-engineer` | Owns level choice and fixtures |
| 24 | A term is contested, or a hard-to-reverse decision needs recording | `domain-modeler` | Owns the glossary and ADRs |
| 25 | `meeting-capture` — listen to, capture, or process a Teams, Zoom, or Meet meeting | `meeting-intelligence` | Checks `status --providers` first; capture, transcript, extraction |

## Chains

Most real requests are one step. These are the sequences worth driving automatically, and each
step is re-gated before the next is dispatched.

| Request shape | Chain | Gate between steps |
| --- | --- | --- |
| Feature, scope not yet agreed | `product-owner` → `software-engineer` → `manual-tester` | Refinement must reach `medium`+ confidence and carry acceptance criteria |
| Reported defect | `issue-investigator` → `software-engineer` | Root-cause status must be `confirmed`, or `suspected` with a discriminating experiment |
| Defect worth pinning | `issue-investigator` → `software-engineer` → `test-automation-engineer` | The scenario must be deterministic before automation |
| Manual defect found during testing | `manual-tester` → `issue-investigator` | The defect must carry environment, build SHA, expected vs actual, steps, evidence |
| Wall of CI failures | `test-automation-engineer` → `issue-investigator` | Only the clusters triage classified `PRODUCT_DEFECT` are handed on, with the evidence that classified them |
| Suite broke after a product change | `test-automation-engineer` | One step, unless triage finds a product defect — then it fans out as above |
| Oversized anything | `delivery-planner` → `delivery-runner` | Readiness must be `READY_FOR_DISPATCH` |
| Oversized anything, nested dispatch unavailable | `delivery-planner` → plan mode, one phase per dispatch | Readiness `READY_FOR_DISPATCH`, and the user confirmed a multi-phase run |
| A phase blocked by its own criterion | phase owner → `delivery-planner` (amend) → phase owner | The blocked artifact shows the contradiction with evidence; once per phase |
| Implementation whose review ran in the writer's context | `software-engineer` → `code-reviewer` over the committed diff | The step committed; the diff range is recorded |
| Answers to a plan's decision gates | `delivery-planner` (amend) → the runner or plan mode | The amended index is back at `READY_FOR_DISPATCH` |
| UX or visual review of an existing page | `manual-tester` or `product-owner` → `product-owner` for anything the user wants changed | The review names its standard, or says there was none |

A chain stops the moment a step returns `blocked` or `needs-context` — with one narrow exception.
When the step's own artifact shows that the **plan** is what cannot be satisfied (its acceptance
or exit criterion contradicts measured behaviour, another phase, or the destination), the owner
of that defect is `delivery-planner`, and the chain goes there instead of to the user. See
[the ambiguous case below](#the-plan-itself-is-wrong). Chains are convenience,
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

**"Write unit tests for the pricing rules I just changed."** `change` →
`software-engineer`, not `automation`. The tests that ship with a code change — unit, the focused
integration tests it needs, its regression test — belong to the engineer who wrote the code, and
the unit-boundary and test-double decisions are part of writing it. Route to
`test-automation-engineer` when the ask is about the *suite*: broader regression automation,
API/system/UI coverage, level strategy, CI, or an existing suite's health.

**"The test is flaky."** `automation` → `test-automation-engineer`, which owns diagnosis. It
becomes `defect` → `issue-investigator` only when the diagnosis finds a real race in production
code rather than in the test — and that finding is the automation engineer's to make, not the
router's to assume from the word "flaky".

**"Fifteen tests broke after the UI refactor."** `automation` → `test-automation-engineer`. Do
not route this to `software-engineer` as a refactor follow-up: whether those tests were wrong or
the refactor broke behaviour is a triage question, and triage is the automation engineer's step.

**"CI has 42 failures."** `automation` → `test-automation-engineer` for triage, always as one
step. Routing the wall to `issue-investigator` assumes 42 product defects; routing it as
maintenance assumes 42 broken tests. Both are guesses the triage step exists to replace, and it
routinely finds that 42 failures are three causes.

**"Our regression suite takes 70 minutes."** `automation` → `test-automation-engineer`, not
`intent-unclear`. This looks like the "it's slow" case above and is not: a test suite's runtime
budget is owned by the engineers who pay it, and the trade — which coverage moves to a lower
level, and what confidence that gives up — is exactly the automation engineer's call. The "it's
slow" rule applies to *product* performance, where the target is a product decision.

**"Automate these 80 manual scenarios."** `automation` → `test-automation-engineer`, and the
step is a backlog decision, not 80 tests. Some are `KEEP_MANUAL`, some belong at a lower level,
some are duplicates. A router that promises 80 automated tests has already made the wrong call.

**"Add API regression coverage for this service."** `automation` → `test-automation-engineer`,
including when it means introducing a level the repository does not test at yet. Adding a harness
inside the existing framework is automation work; replacing the framework is a decision that
needs a named human owner, and the automation engineer stops and says so.

### Is this `oversized-input` or just a big file?

The distinction is what the user asked for, not how big the attachment is.

**"Extract what matters from this 150 MB log for the payment failure."** `oversized-input` →
`context-optimizer`. Reducing the evidence is the deliverable.

**"Payments are failing, here is the log."** `defect` → `issue-investigator`. The deliverable is a
root cause. That skill calls `agent-skills context pack` itself as its first step; routing to
Context Optimizer first would add a dispatch, a fresh agent's context, and a handoff to save one
command.

**"This diff is 40,000 lines, find the security-relevant changes before I review it."** Judgement
call, and either answer is defensible. `context-optimizer` when the ask is genuinely "make this
reviewable"; `code-reviewer` when a verdict is wanted, since it packs the diff itself. Prefer
`code-reviewer` — it owns the verdict, and a pack without one is half an answer.

**"Our regression suite log is 2 GB and CI has 42 failures."** `automation` →
`test-automation-engineer`. Triage owns this, and it packs the log as part of triage.

The rule of thumb: route to `context-optimizer` when the **pack** is the deliverable. Route
elsewhere when the pack is a step toward one.

### The plan itself is wrong

**A phase blocked on its own acceptance criterion.** A phase required moving an add-on option
off the price screen, and its executor measured that option moving the price 4.6× — an input
that large cannot leave the screen where the price is shown. The phase was not blocked on missing work, access, or evidence. It was
blocked because what it asked for cannot be true. Stopping and asking the user costs a round
trip nobody needed; retrying costs the same failure twice; routing to a different executor to
"find another way" is routing around a blocker. The defect is in the plan, and the plan has an
owner: `plan-amendment` → `delivery-planner`, with the blocked artifact as its evidence.

The distinction has to come from the artifact, not from a feeling about the phase:

- **Blocked by something outside the plan** — a dependency not merged, access not granted,
  evidence not yet gathered, a check that failed. Stop, as always.
- **Blocked because the plan is wrong** — the artifact states which criterion, what was measured
  or read, and why the two cannot both hold. Route to the planner once. If the amended criterion
  is contradicted again, stop and hand it to the user: two wrong plans in a row is a product
  question, not a planning one.

"Hard", "slow", "bigger than estimated", or "I would have done it differently" are not
contradictions. The watchdog's `narrow` and `split` verdicts already route those to the planner
through the runner's stop conditions.

**"Here are my answers to your decision gates."** Not a defect, a change, a question, or a review.
The plan carried open decisions, the user has closed them, and the plan must now say so before
anything runs against it. `plan-amendment` → `delivery-planner`. Do not paste the answers into
the next phase's brief instead: the next phase would honour them and every later one would not.

### Reviewing something that is not a diff

**"Review this page's UX."** `design-review`, not `review`: row 16 is for an existing diff,
branch, or PR, and a page is none of those. The owner depends on what the review is measured
against.

- A stated standard exists — a design system, acceptance criteria, an accessibility level, the
  viewports that must work — → `manual-tester`. Observed against expected, with evidence, and
  usability observations kept apart from defects.
- No standard, and the question is whether the experience is right → `product-owner`. Its output
  is UX notes and refinement input, never edits to the page.

Either way the step is read-only, and the brief says so. A review that edits what it reviews has
graded its own work.

**A bare ticket key with nothing else.** Do not classify from the key. Fetch the ticket if the
capability report says a tracker resolves; if it does not, ask the user for the summary and
acceptance criteria. Guessing intent from a key or a branch name is a documented failure mode.

**A request that is really two requests.** Split it, route the first, and say plainly that the
second is waiting. Do not average two requests into one destination.

## Known gaps

Requests the canonical skill set has no owner for. Each has been reached for in real use; each is
written down so the next dispatcher does not re-derive the reasoning, and does not route the
request somewhere that merely looks close.

- **Authoring a visual design** — a new look, a design system, layout or typography direction.
  `product-owner` owns UX intent and `manual-tester` observes against a standard; neither creates
  one. Say it is a known gap, and offer `product-owner` for the intent and constraints the design
  must meet. Never dispatch a skill outside the canonical set.
- **A design review from a tool that fixes as it reviews.** Reviewing and editing in one context is
  the independence failure `code-reviewer` exists to prevent. Route the review as `design-review`,
  read-only; any change follows as its own `change` step.
- **Deleting anything that is not a file** — branches, tracker items, database rows, cloud
  resources. Nothing can prove those recoverable. The safety floor applies: an unmerged or unpushed
  branch is not deleted, and production data gets an operator runbook.

A gap is closed by adding a skill or widening an owner in
[skill boundaries](../../../docs/skill-boundaries.md) first, then a row here. Never by routing.

## Routes that do not exist

Worth stating, because each is a plausible-looking mistake:

- **Never route to `code-reviewer` inside an implementation step.** The engineer runs that loop
  itself. A lead that also dispatches the reviewer while that step is running creates two review
  loops and breaks the depth cap. Row 15 is not that: it runs after the step has committed and
  returned, only when the step recorded that its review could not run in a fresh context, and it
  reviews the committed diff. See [independent review](./dispatch-topology.md#independent-review).
- **Never route to `delivery-planner` mid-step.** If a step turns out to be oversized, the step
  stops and surfaces; the planner re-decomposes on its next run. Between steps, a plan that
  must change is a `plan-amendment` (row 2), and that is a normal route, not recursion.
- **Never route to `wamala`.** No skill invokes itself, directly or transitively.
- **Never route around a blocker.** A blocked step means stop, not "try a different skill".

## Recording what the routing got wrong

A misclassified request shape is a durable lesson about this project, which is exactly what the
[repo knowledge base](../../../docs/repo-knowledge.md) is for:

```bash
agent-skills knowledge lesson add \
  --id perf-requests-need-a-target \
  --trigger "when a request says something is slow" \
  --action "ask for the target or SLA first; without one there is no defect to investigate" \
  --domain process
```

Over time these accumulate into routing that fits the project rather than the generic table.
