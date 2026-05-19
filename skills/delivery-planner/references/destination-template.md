# Destination Template

The binding shape of `destination.md` written by `delivery-planner` to
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<work_key>/destination.md`.

`destination.md` is the one-page brief any executor pastes alongside one
phase to have a complete picture of the goal. Keep it short — if it does
not fit on a phone screen, the agent has not actually scoped the work.

Do not invent extra fields. If something is genuinely not applicable, write
`not applicable — <one-line reason>` instead of removing the field. Empty
fields hide assumptions; named-and-empty fields do not.

## File header

```yaml
---
work_key: AUTH-SSO-PARITY     # Tracker key, GitHub issue number, or local slug
                              # (lowercase-hyphen-separated when no ticket exists,
                              # e.g. local-2026-05-auth-sso-parity)
title: SSO parity for the example-api login flow
state: draft | active | superseded   # active = currently the dispatch source;
                                     # superseded = a newer destination replaced it,
                                     # kept on disk so back-references still resolve
created_at: 2026-05-06
updated_at: 2026-05-06        # MUST bump on every in-place edit
source_refs:                  # pointers to the inputs this destination came from
  - "ticket: AUTH-SSO-PARITY"
  - "doc: docs/auth.md"
  - "incident: INC-1042"
understanding_confidence: high   # unknown | low | medium | high
                                 # mirrors the gate's value at the time of writing
readiness_decision: READY_FOR_DISPATCH   # READY_FOR_DISPATCH | READY_FOR_DISCOVERY |
                                         # NEEDS_CLARIFICATION | NEEDS_EVIDENCE | BLOCKED
---
```

## Body sections

```markdown
# SSO parity for the example-api login flow

## Outcome

One or two plain-language sentences. The first sentence describes what
changes from the user's perspective; the second (if any) describes what
changes from the system's perspective. No vendor names, fashion words,
or metaphors.

## Success signals

Two to five observable signals that mean the outcome was achieved. Each
signal MUST name what observes it (manual check, automated test, log
filter, dashboard widget, metric query).

- `<signal>` — observed by `<who/what>`.
- `<signal>` — observed by `<who/what>`.
- ...

## Scope

What this delivery includes. Be specific enough that the executor can
tell whether a given file or workflow falls inside.

## Non-goals

What this delivery deliberately does not include, even when adjacent or
tempting. The most-skipped field and the most expensive to omit. If
truly empty, write `none — bounded by the success signals above`.

## Constraints

Hard limits: deadline, compliance, downtime windows, freeze periods,
dependent teams, environment access, headcount. "Soon" / "secure" /
"scalable" are not constraints.

## Load-bearing assumptions

Each labelled `safe` or `load-bearing`. Every `load-bearing` one MUST
carry a one-line *what would change my mind* falsifier.

- `<assumption>` (load-bearing) — would change my mind: `<observation>`.
- `<assumption>` (safe).

## Stakeholders / decision makers

Named by role (not just team). Identify who must agree before:
the plan executes, scope changes, destructive-action approvals.

- Scope changes: `<role>`.
- Phase reviews: `<role>`.
- Destructive-action approvals: `<role>`.

## Risks the plan protects against

Two to four named risks (data corruption, customer-visible regression,
rollout cost, compliance breach, cross-team coupling) so phases can be
scheduled to retire the highest-risk ones first.

- `<risk>` — first phase that retires it: `<phase id>`.
- `<risk>` — first phase that retires it: `<phase id>`.
```

## Update discipline

- Bump `updated_at:` on every edit.
- Never change `work_key:` after the file is created — downstream
  artifacts reference the slug.
- When the destination materially changes (outcome, success signals, or
  non-goals), set `state: superseded` on the old file, write a fresh
  `destination.md` next to it under `destination-vN.md` (or rotate the
  current one to `destination-v1.md` and rewrite `destination.md`),
  then re-run the planner so it re-decomposes.
- Keep `understanding_confidence:` and `readiness_decision:` in sync
  with the per-run [Requirement Understanding
  Gate](../SKILL.md#0-requirement-understanding-gate). A destination
  whose stored confidence disagrees with the latest gate is the
  planner's signal that the file is stale.
