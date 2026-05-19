# Domain Modeler

Maintains a living domain glossary (`CONTEXT.md`) and generates Architecture Decision Records
(ADRs) sparingly.

## What it does

- Creates and maintains `CONTEXT.md` — a canonical, opinionated glossary of domain terms.
- Generates `docs/adr/NNNN-slug.md` ADRs only when the 3-criteria gate is met (hard to
  reverse, surprising without context, result of a real trade-off).
- Challenges user statements against the existing glossary, sharpens fuzzy terminology,
  cross-references stated behaviour against code, and stress-tests domain relationships
  with concrete edge-case scenarios.

## When to use it

- A plan or feature needs stress-testing against established domain language.
- Terminology is ambiguous across stakeholders, tickets, or docs.
- An architectural decision needs a recorded rationale.
- The user wants to establish or update a canonical glossary.

## Quick start

```bash
# In local-workspace mode, the skill reads from the same config:
source "${WORKSPACE_ROOT}/.env"
```
