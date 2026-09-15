# Run Preamble Template

The constraints every step of one Wamala run shares, written once and referenced from every
brief.

In one real run, each handoff re-specified the same rules: work on branch `dev`, do not push,
run `git status` first, no destructive operations, measure at 360×640, resolve colours through a
1×1 canvas, run the knowledge-base lint, write to the durable directory rather than the cache,
run the lifecycle wrappers. Ten briefs of 1,000–2,500 words each, mostly repeated. Repetition
also drifts: the tenth copy is the one where a rule gets dropped.

## Where it lives

```text
<cache-dir>/<work-key>/artifacts/run-preamble.md
```

`artifacts/` survives every cleanup, so the preamble outlives each step's closeout. Wamala is its
only writer. A dispatched step that discovers a constraint binding every later step reports it
in `follow_up_context`, and Wamala moves it into the preamble.

## Rules for filling it

- **Resolve it once**, at the start of the run, from what already exists: the user's instructions
  in this conversation, `.agent-skills.yml`, project memory, the repo knowledge base, and the
  capability report. Cite each line's source in brackets.
- **Do not invent a constraint.** If the branch policy is unknown, the line reads
  `unknown — ask before the first write`, not a guess.
- **Recorded facts are claims.** A knowledge-base trap goes in as a pointer plus the one line
  that binds, and a step that disproves it corrects the record.
- **Never a secret.** No token, password, connection string, or credential-bearing URL. Access
  is resolved per step through the Access Resolver.
- **One screen.** About sixty lines. A preamble that grows past that is carrying step detail that
  belongs in a brief, or reference material that belongs behind a pointer.

## Template

```markdown
# Run preamble — <work-key>

Every step of this run follows this file. Your brief adds only what is specific to your step.

## Identity
- Project: <project> · Work key: <work-key> · Cache: <cache-dir>/<work-key>/
- Start: `agent-skills start-task --project <project> --issue-key <work-key> --skill <owner> --brief "<step>"`
- Finish: `agent-skills finish-task --project <project> --issue-key <work-key> --skill <owner> --status <status> --summary "<outcome>"`
  Scratch is left for Wamala to verify and clean; do not pass `--cleanup`.
- Nested dispatch: <available | unavailable> [<how it was established>]

## Repository rules
- Branch: <branch> [source] · Base: <base> · Push: <never | on PR only | ...> [source]
- Before any write: `git status`; stop if the tree has changes you did not make.
- Destructive operations: none without an explicit instruction in your brief.
  <delete-shaped work in this run: archive to <path>; the user runs any delete>

## Where output goes
- Durable deliverables: <repo path, e.g. docs/audits/> [source]
- Evidence and working notes: <cache-dir>/<work-key>/artifacts/<step-slug>/
- The evidence pack and checkpoint: <cache-dir>/<work-key>/evidence-pack.yml

## How to measure and check
- <recipe, e.g. viewport 360×640; resolve computed colours through a 1×1 canvas> [source]
- <lint/validate command, e.g. `kb lint`> [source]
- Verification bar for this run's class: see references/verification-bars.md#<class>

## Known traps
- <one line each, with the knowledge-base id or file it came from>

## Owner skills
- Canonical skill source: <resolved path>
- Owners used this run: <owner> → <path>/SKILL.md, ...
```

## What stays in the brief

The brief keeps the request, the step's classification and profile, the output contract, the
scope boundary and what is explicitly **not** this step, the effort budget, the carried-forward
context from its prerequisites, and one line:

```text
Run preamble (BINDING): read <cache-dir>/<work-key>/artifacts/run-preamble.md first.
```

A brief built this way runs to a few hundred words, and the constraints do not change between
the first step and the tenth.
