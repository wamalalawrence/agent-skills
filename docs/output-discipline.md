# Output Discipline

Every skill in this repository ships with an `Expected Output Contract` that lists the
sections the agent **may** emit. The contract is a **maximum**, not a checklist to fill
in. The agent must keep its output short, scannable, and free of template noise — the
review you produce should look like a careful engineer's review, not a form-filled
audit report.

This page is the canonical reference. Every `SKILL.md` links here from inside its
Expected Output Contract, and `scripts/validate-repo.py` enforces that the rules below
appear in each skill so they cannot drift apart.

## Hard rules (every skill, every run)

1. **Omit empty sections.** If a section in the contract has nothing to say, do not
   render the heading at all. Do **not** emit placeholder lines like `- none`,
   `- n/a`, or empty bullet stubs just because the template lists the section. The
   only exceptions are explicitly marked **Required-even-if-empty** sections (for
   `code-reviewer`, that is exactly the one-line `Final Verdict`).
2. **Do not echo the request.** Do not restate the user's prompt, the URL, or the
   ticket key as a paragraph before the result. The header line at the top is enough.
3. **One section, one purpose.** If the same fact would appear in two sections,
   write it once and link by name. Never repeat content across `Findings`,
   `Engineering Quality`, and `Review Limitations`.
4. **Bullet-first.** Prose paragraphs are reserved for the Devil's-Advocate rebuttal
   and the Final Verdict reason. Everything else is bullets, ≤ 2 lines per bullet.
5. **No template skeletons.** Never paste the contract's section list with empty
   values. The contract describes the **shape** of the output, not the output itself.
6. **No verbose status decorations.** Do not emit `Status: ✅ PASS`, banners, ASCII
   rules, or block quotes around the verdict line. Just the verdict word.
7. **No restating of the workflow.** The user does not need a recap of which steps
   the skill ran. Surface only the **result** of each step that produced one.

## Findings format (code-reviewer, manual-tester defects, investigator hypotheses)

Each finding is **one bullet, one paragraph max**:

```markdown
- **<severity>: <one-line title>** — <evidence in 1 sentence>. Why it matters: <1
  sentence>. Fix: <1 sentence>. (confidence: high|medium|low; blocking|advisory)
```

You may break to a second paragraph **only** when the evidence is a quoted code
snippet or stack trace that does not fit on one line. Do not split a finding into a
seven-bullet sub-list of "Severity:", "Title:", "Affected file:", "Evidence:",
"Why it matters:", "Suggested fix:", "Confidence:", "Blocking decision:". That is
the form the contract describes — not the form the agent emits.

## Limitations format

Render `Review Limitations / Unavailable Context` (or its equivalent in other skills)
as **at most one paragraph** listing only the items that actually limited the
review. If everything was available, write one line:

```markdown
- Review Limitations: none.
```

Do **not** render a six-bullet block where every item says `none`.

## Verdict / final-status format

The verdict is **one line**, optionally followed by **one** "Reason:" line and one
"Follow-up:" line. Do not wrap it in quotes, asterisks, or a banner.

```markdown
## Final Verdict

PASS_WITH_NOTES — TS-05 plausibly addressed, TS-04 not in scope of this PR.
Follow-up: revert PaymentOrder fetch changes to LAZY; add a test for the null path.
```

## What "tightened" looks like in practice

A code-reviewer run on a 5-file PR should comfortably fit on a phone screen when
findings are ≤ 4. Two screens is the upper bound for ≤ 10 findings. If the rendered
output is longer, the agent is almost certainly echoing the template.

The
[`code-reviewer-concise-output`](../evals/code-reviewer-concise-output.md) eval pins
this expectation with a worked example.

## The output contract

Every dispatch may carry an **output contract**: not what question to answer, but what artifact
the human on the other end actually needs.

```yaml
output_contract:
  audience: engineering meeting
  primary_question: how many payments failed in each of the three systems yesterday?
  deliverable: one compact table
  reading_time_target: under 30 seconds
  evidence_depth: retained-separately
  evidence_location: .cache/agent-skills/PROJ-1234/evidence/
```

Fields: `audience`, `primary_question`, `deliverable`, `reading_time_target`, `evidence_depth`
(`cited-inline` | `retained-separately` | `none`), and `evidence_location` when evidence is kept
apart.

**The primary deliverable is not automatically the evidence artifact.** This is the rule the
contract exists for. A request for three numbers received two citation-heavy reports over 40 KB
each, because the skill that was dispatched builds evidence trails and nobody had told it the
answer needed to be readable in half a minute. Both things were wanted; only one of them was the
deliverable.

So evidence is **preserved, not suppressed** — written to `evidence_location` and referenced by
one line. Depth of investigation and size of answer are separate decisions, and collapsing them
is what produced the dossiers.

There is deliberately **no global character limit**. A hard cap would truncate the one review
that genuinely needed nine findings. The contract states the target for *this* piece of work,
and the skill meets it.

When no contract is supplied, infer one from the request and say what you inferred in a single
line. "You asked in a meeting context, so this is a table; the full query output is at `<path>`"
costs nothing and lets the reader correct you.

## Why this exists

Real reviewers signal expertise by what they leave **out**. A review that mechanically
fills every section of a template — including the empty ones — looks like a checklist
exercise and buries the actual blockers underneath section headers. The verbose
output is also harder to act on, harder to skim in a PR comment, and harder to
trust.

The agent must therefore treat the Expected Output Contract as a **menu of available
sections**, not a list of headings to print.

## Enforcement

`scripts/validate-repo.py` enforces, for every `SKILL.md`:

- Each `## Expected Output Contract` section contains a sub-heading or paragraph
  that links to this file (`docs/output-discipline.md`) — so contributors cannot
  silently drop the rule.
- Each `## Expected Output Contract` section contains the literal phrase
  `Omit empty sections` so the most important hard rule is restated inline.

The validator does not inspect actual model output — it ensures the **specification**
the agent loads contains the rule. The
[`code-reviewer-concise-output`](../evals/code-reviewer-concise-output.md) eval is
where actual transcripts are pinned against the rule.
