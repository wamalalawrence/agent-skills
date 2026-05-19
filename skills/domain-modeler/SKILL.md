---
name: domain-modeler
description: >-
  Domain modeling workflow that maintains a living glossary of canonical terms
  (CONTEXT.md) and generates Architecture Decision Records (ADRs) sparingly when a
  decision is hard to reverse, surprising without context, and the result of a real
  trade-off. Use when: stress-testing a plan against the project's domain language,
  sharpening fuzzy terminology, recording architectural decisions, cross-referencing
  stated behaviour against code, or resolving ambiguous terms before implementation.
  Collaborates with product-owner for product terminology and scope, software-engineer
  for technical architecture decisions, and delivery-planner for documenting
  phase-level architectural choices.
license: MIT
compatibility: >-
  Works with any agent that supports the Agent Skills format (Claude Code, Cursor,
  Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Two execution modes —
  `local-workspace` (multi-repo, setup.init + .env) and `in-repo` (single-repo,
  .agent-skills.yml). See docs/execution-modes.md.
metadata:
  author: wamalalawrence
  version: "0.30.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
---

# Domain Modeler

Use this skill to maintain a living domain model — a canonical glossary of terms and a record of
significant architectural decisions — that keeps the project's language precise and its design
rationale accessible.

The agent behaves like a domain-driven design partner: it captures terminology as it crystallises,
challenges fuzzy or conflicting language against the existing glossary, stress-tests domain
relationships with concrete scenarios, cross-references stated behaviour against the codebase,
and records architectural decisions only when they are genuinely hard to reverse, surprising, and
the result of a real trade-off.

> **Safety floor.** This skill inherits the
> [destructive-action safety policy](../../docs/destructive-action-safety.md). It is read-only
> except for writing `CONTEXT.md`, `CONTEXT-MAP.md`, and `docs/adr/*.md` files into the
> repository. It must never modify production code, configuration, or infrastructure.

## Purpose

- Maintain a **CONTEXT.md** glossary of canonical domain terms — one or two sentences per term,
  listing aliases to avoid, grouped under natural subheadings. The glossary is opinionated: when
  multiple words exist for the same concept, pick the best one and list the others as aliases.
- Generate **Architecture Decision Records (ADRs)** sparingly — only when all three criteria are
  met: (1) hard to reverse, (2) surprising without context, (3) the result of a real trade-off
  with genuine alternatives. Skip the ADR if any criterion is missing.
- Challenge user statements against the existing glossary. When a term conflicts with the
  documented language, call it out immediately.
- Sharpen fuzzy or overloaded terms by proposing precise canonical alternatives.
- Cross-reference stated behaviour against the codebase. When the code contradicts what the user
  claims, surface the contradiction.
- Stress-test domain relationships with concrete edge-case scenarios that force precision about
  boundaries between concepts.

## When To Use

- A plan, feature, or refactor needs to be stress-tested against the project's established
  domain language.
- Terminology is ambiguous across stakeholders, tickets, or documentation.
- A significant architectural decision has been made and its rationale should survive beyond the
  current team.
- The user wants to establish or update a canonical glossary for the project or a specific
  bounded context.
- Code and documentation disagree about what a term means or how a relationship works.
- An `ADR` is needed to prevent a future reader from "fixing" something that was deliberate.

## When Not To Use

- Do not use for every implementation decision. Most choices are easy to reverse, unsurprising, or
  have only one obvious path — those do not need an ADR.
- Do not use to replace product refinement or acceptance criteria; use
  [`product-owner`](../product-owner/SKILL.md).
- Do not use to dictate technical architecture; collaborate with
  [`software-engineer`](../software-engineer/SKILL.md) for feasibility and trade-offs.
- Do not treat `CONTEXT.md` as a spec, scratch pad, or implementation-detail repository. It is a
  glossary and nothing else.
- Do not create ADRs for decisions that are trivially reversible, obvious to future readers, or
  had no real alternative.

## Related And Reused Skills

- [`product-owner`](../product-owner/SKILL.md): collaborates on product terminology, scope
  boundaries, user-facing language, and stakeholder vocabulary. Product-owner owns what users
  call things; domain-modeler owns what the system calls things internally and how those terms
  relate.
- [`software-engineer`](../software-engineer/SKILL.md): collaborates on architectural decisions,
  implementation trade-offs, technology choices, and integration patterns. Software-engineer
  owns the implementation; domain-modeler owns documenting *why* the implementation made a
  particular choice.
- [`delivery-planner`](../delivery-planner/SKILL.md): ADRs generated during planning phases
  are referenced by the planner's `destination.md` as architectural context. Domain-modeler
  does not produce phases.
- [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md): when
  investigation reveals that a term is used inconsistently across tickets, docs, and code,
  domain-modeler resolves the canonical term.
- [`code-reviewer`](../software-engineer/skills/code-reviewer/SKILL.md): when review finds
  that code introduces a new term or contradicts the glossary, domain-modeler updates
  `CONTEXT.md` or records an ADR.

Domain modeling captures the project's language and design rationale. It does not implement code,
write tests, or define product scope.

## Required Inputs

Ask for missing information before writing or updating glossary entries or ADRs.

- The term, concept, or decision to model.
- The affected bounded context or system area.
- Existing documentation, tickets, or code references that use the term.
- Stakeholder perspectives when a term is contested.
- For ADRs: the alternatives considered, the trade-off made, and why the decision is hard to
  reverse, surprising, or non-obvious.

## Stopping Conditions

Stop and return clarification questions instead of writing when:

- The term is used inconsistently across stakeholders and no authoritative source is available.
- An ADR is requested but none of the three criteria (hard to reverse, surprising, result of a
  real trade-off) are met. Offer to skip the ADR instead.
- The glossary entry would require inventing domain facts that were not supplied.
- The codebase and documentation disagree fundamentally and neither is clearly authoritative.

## File Structure

Most repos have a single context:

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple bounded contexts. The map
points to where each context's `CONTEXT.md` lives:

```
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily — only when you have something to write. If no `CONTEXT.md` exists,
create one when the first term is resolved. If no `docs/adr/` exists, create it when the
first ADR is needed.

## Required Workflow

### 0. Requirement Understanding Gate

Run the shared [requirement-understanding workflow](../../docs/requirement-understanding.md)
before writing any glossary entry or ADR. Emit the `Requirement Understanding` block above
the rest of the output.

Apply the binding rules:

- **`unknown` / `low`** — do not write a glossary entry or ADR. Return `NEEDS_CLARIFICATION`
  with the specific ambiguity that must be resolved.
- **`medium`** — may draft glossary entries with `assumed definition` annotations and open
  questions. May not write an ADR until assumptions are confirmed.
- **`high`** — may write final glossary entries and ADRs.

### 1. Domain awareness

During codebase exploration, also look for existing documentation:

- Scan for `CONTEXT.md` at the repo root, or `CONTEXT-MAP.md` then per-context files.
- Scan `docs/adr/` for existing ADRs.
- Check `README.md`, `CONTRIBUTING.md`, and any `docs/` pages for existing terminology.
- Check recent tickets, PR descriptions, and code comments for terms used in practice.

### 2. Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it
out immediately. Example: *"Your glossary defines 'cancellation' as voiding the entire order,
but you seem to mean partial line-item removal — which is it?"*

If no `CONTEXT.md` exists yet, note that a glossary will be created as terms are resolved.

### 3. Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. Example:
*"You're saying 'account' — do you mean the Customer or the User? Those are different things
in this system."*

Pick the best term and list alternatives as "Avoid" entries in the glossary.

### 4. Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios.
Invent scenarios that probe edge cases and force precision about the boundaries between
concepts. Example: *"If a Customer has multiple Users and one User cancels — does that affect
the Customer's other Users?"*

### 5. Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a
contradiction, surface it: *"Your code cancels entire Orders (see `OrderService.cancel()`),
but you just said partial cancellation is possible — which is right?"*

This is not a code review — it is verifying that the domain language matches the
implementation reality.

### 6. Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Do not batch these up — capture
them as they happen. Use the format in [CONTEXT-FORMAT.md](./references/CONTEXT-FORMAT.md).

**Rules for CONTEXT.md:**

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and
  list the others as aliases to avoid.
- **Flag conflicts explicitly.** If a term is used ambiguously, call it out in "Flagged
  ambiguities" with a clear resolution.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Show relationships.** Use bold term names and express cardinality where obvious.
- **Only include terms specific to this project's context.** General programming concepts
  (timeouts, error types, utility patterns) do not belong even if the project uses them
  extensively. Before adding a term, ask: is this a concept unique to this context, or a
  general programming concept? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge. If all terms belong to a
  single cohesive area, a flat list is fine.
- **Write an example dialogue.** A conversation between a dev and a domain expert that
  demonstrates how the terms interact naturally and clarifies boundaries between related
  concepts.

`CONTEXT.md` must be totally devoid of implementation details. Do not treat it as a spec,
a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### 7. Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful.
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one
   for specific reasons.

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](./references/ADR-FORMAT.md).

**What qualifies for an ADR:**

- **Architectural shape.** "We're using a monorepo." "The write model is event-sourced,
  the read model is projected into Postgres."
- **Integration patterns between contexts.** "Ordering and Billing communicate via domain
  events, not synchronous HTTP."
- **Technology choices that carry lock-in.** Database, message bus, auth provider,
  deployment target. Not every library — just the ones that would take a quarter to swap out.
- **Boundary and scope decisions.** "Customer data is owned by the Customer context; other
  contexts reference it by ID only." The explicit no-s are as valuable as the yes-s.
- **Deliberate deviations from the obvious path.** "We're using manual SQL instead of an
  ORM because X." Anything where a reasonable reader would assume the opposite.
- **Constraints not visible in the code.** "We can't use AWS because of compliance
  requirements." "Response times must be under 200ms because of the partner API contract."
- **Rejected alternatives when the rejection is non-obvious.** If you considered GraphQL and
  picked REST for subtle reasons, record it — otherwise someone will suggest GraphQL again
  in six months.

**What does NOT qualify:**

- Every library choice. Only the ones with meaningful lock-in.
- Decisions that are easy to reverse (you'll just reverse them).
- Decisions that are unsurprising (nobody will wonder why).
- Decisions with no real alternative (there's nothing to record beyond "we did the obvious
  thing").

ADRs live in `docs/adr/` and use sequential numbering: `0001-slug.md`, `0002-slug.md`, etc.
Create the `docs/adr/` directory lazily — only when the first ADR is needed. Scan `docs/adr/`
for the highest existing number and increment by one.

### 8. When invoked from a delivery-planner phase

If this run was invoked because a [`delivery-planner`](../delivery-planner/SKILL.md) phase
named `domain-modeler` as its `recommended_owner`:

- Read `destination.md` and the current `phase-NN-<slug>.md` from
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/`
  before starting.
- Treat the phase's `Inputs`, `Scope`, and `Validation` as the authoritative brief.
- The phase's `Expected outputs` typically names the `CONTEXT.md` or `docs/adr/NNNN-slug.md`
  to produce.
- Do not refine outside the phase's stated scope.
