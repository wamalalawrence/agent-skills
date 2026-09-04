# Example: tech-lead routing a reported defect

A worked run of [`tech-lead`](../../skills/tech-lead/SKILL.md) on a request that sounds like it
names its own fix, and does not.

## Prompt

```text
Use the tech-lead skill: invoice search drops the status filter when you go to page 2.
```

## What the skill does

Preflight first, which prints project memory, the repo knowledge base, and the capability
report. Then classification, then the requirement-understanding gate, then a route.

The gate is what changes the answer here. The symptom is clear and the fix sounds obvious —
carry the filters through the URL builder — but no root cause has been established. Guessing at
the mechanism and fixing the guess is the failure this ordering prevents.

## Output

```markdown
## Routing Decision

- Lifecycle: start-task=ran; finish-task=ran; memory=updated; skill=tech-lead@0.36.0
- Request: page 2 of invoice search loses the selected status filter
- Class: defect
- Understanding confidence: high
- Routed to: issue-investigator — the symptom is specific and reproducible, but no
  root cause is recorded and the fix location is a guess
- Chain: issue-investigator -> software-engineer
- Dispatch mechanism: sub-agent

## Steps

- **issue-investigator** — done. Verified by:
  `.cache/agent-skills/ABC-123/evidence-pack.yml`. Root cause confirmed: the
  next/previous URL builder carries only the page number, dropping every active
  filter. Deterministic reproduction recorded.
- **software-engineer** — done. Verified by: PR URL in
  `.cache/agent-skills/ABC-123/definition-of-done.json`. Failing test committed
  first, then the fix; full suite green.

## Open Questions Or Missing Evidence

- Sort order may have the same defect — the same builder handles it, and nobody has
  checked. Not in scope for this fix.
```

## What to notice

**The route contradicts the obvious reading.** "Drops the status filter" points straight at the
filter code. The lead routed to investigation anyway, because "specific symptom" and "known
cause" are different things. The investigation found the bug in the URL builder, not the filter
code — so a fix dispatched directly would have been aimed at the wrong file.

**The reason cites evidence, not the destination.** "No root cause is recorded and the fix
location is a guess" is checkable. "Routed to issue-investigator for investigation" would say
nothing.

**Each step was verified from disk.** The evidence pack proves the investigation happened; the
definition-of-done file proves the PR exists. Neither is taken from the dispatched agent's chat.

**The second handoff carried paths, not findings.** The `software-engineer` agent read the
evidence pack itself. Pasting the investigation into the brief would rebuild exactly the
accumulated context that fresh-context dispatch exists to avoid.

**The open question is stated, not resolved.** Sort order probably has the same defect. The lead
records it and stops rather than expanding scope, because that is a decision for the person who
asked.

## The same request, three variations

| Request | Class | Route | Why |
| --- | --- | --- | --- |
| "Page 2 drops the status filter" | `defect` | `issue-investigator` | Symptom is clear, cause is not |
| "Page 2 drops the status filter, cause is in `UrlBuilder.next()`" | `defect` | `software-engineer` | Cause supplied and checkable |
| "Pagination feels wrong" | `intent-unclear` | `product-owner` | No expected behaviour to violate yet |

The third is the one worth dwelling on. Without a statement of what pagination *should* do,
there is no defect — only a preference. Routing it to engineering produces a change nobody can
validate.

## When to skip this skill

If you already know the owner, invoke it directly. `Use the issue-investigator skill on ABC-123`
is faster and better than routing to it. `tech-lead` earns its place when the classification is
genuinely the hard part.

## Related

- [Routing table](../../skills/tech-lead/references/routing-table.md) — the full mapping,
  including the ambiguous cases.
- [Requirement understanding](../requirement-understanding.md) — the gate that reordered this
  decision.
- [Skill boundaries](../skill-boundaries.md) — who owns what.
