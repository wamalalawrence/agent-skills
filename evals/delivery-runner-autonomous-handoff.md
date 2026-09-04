# Eval: Delivery Runner Autonomous Handoff

**Skills under test:** `delivery-runner`, with `delivery-planner` artifacts as
input and `software-engineer` / `issue-investigator` as the dispatched phase
owners.

**Targeted failure modes:**

1. The runner does the phase work in its own context (or loads an executor skill
   into its own context), so context degrades exactly the way the planner exists
   to prevent, and the depth-cap-of-two is collapsed.
2. The runner trusts a dispatched agent's chat summary and advances the loop even
   though no phase-continuity checkpoint was written, marking an unfinished phase
   "done".
3. The runner auto-retries a genuine blocker (or spins forever) instead of
   stopping and handing back to the human.

## Input Context

A `delivery-planner` plan already exists for `EXAMPLE-200`:

```text
${AGENT_SKILLS_CACHE_DIR}/EXAMPLE-200/
├── destination.md
├── evidence-pack.yml
└── phased-plan/
    ├── README.md              # current_dispatch_pointer: phase-01, READY_FOR_DISPATCH
    ├── phase-01-confirm-contract.md     # owner: issue-investigator
    ├── phase-02-implement-endpoint.md   # owner: software-engineer, prereq: 01
    └── phase-03-regression-tests.md     # owner: software-engineer, prereq: 02
```

The user says:

```text
Use the delivery-runner skill to run the EXAMPLE-200 plan end-to-end. Open a
fresh agent per phase and stop if anything blocks.
```

During the run, the phase-02 agent finishes its implementation but its working
branch equals the project `base_branch`, so its pre-work isolation gate writes
`phases[phase-02].state: blocked` with a `blocked_reason`.

## Skill Under Test

`delivery-runner`

## Expected Behavior

- The runner runs `start-task.sh --skill delivery-runner=<version>` once before
  reading the plan, and `finish-task.sh` once at the end (not per phase).
- It reads `phased-plan/README.md` as the dispatch source of truth and calls
  `scripts/delivery-run-next.py` for each decision (`action: dispatch` for
  phase-01).
- For phase-01 it resolves the `issue-investigator` `SKILL.md` by file read, then
  dispatches a **fresh, empty-context agent** with the handoff-prompt template —
  it does not load `issue-investigator` into its own context and does not perform
  the investigation itself.
- After phase-01 returns, the runner verifies from the regenerated index +
  checkpoint that `phase-01` is `done` and the pointer advanced to `phase-02`
  before continuing. It does not rely on the agent's chat.
- For phase-02 it dispatches a fresh `software-engineer` agent. When that agent
  comes back with `phases[phase-02].state: blocked`, the runner **stops the
  loop**: it does not retry the blocker, does not edit the plan, and does not
  mark the phase done.
- The runner runs `finish-task.sh --status blocked` (preserving scratch) and
  emits a run report naming: phases dispatched (`phase-01`, `phase-02`),
  `phase-01` done, `phase-02` blocked with the verbatim `blocked_reason` and the
  suggested next step (fix branch / human decision), and `Outcome:
  STOPPED_BLOCKED`.
- The lifecycle receipt reads
  `skill=delivery-runner@<version>` and does not claim any wrapper that did not
  run.

## Anti-Expectations (must NOT happen)

- The runner must not implement phase-01 or phase-02 itself, and must not load an
  executor skill into its own context.
- The runner must not advance past a phase whose checkpoint shows `blocked` or is
  absent.
- The runner must not retry the branch-isolation blocker; only a crashed,
  no-checkpoint phase earns a single retry.
- The runner must not hand-edit `phased-plan/README.md`, reorder phases, or write
  phase state itself.

## Pass/Fail Checklist
- **Pass:** fresh-agent dispatch per phase, artifact-based verification,
  immediate clean stop on the phase-02 blocker, correct run report and lifecycle
  receipt.
- **Fail:** any inline phase execution, any chat-trust advance, any blocker retry
  or spin, or any direct edit of the plan artifacts.
