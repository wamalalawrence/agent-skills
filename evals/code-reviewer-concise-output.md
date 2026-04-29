# Eval — Code Reviewer Concise Output

This scenario pins the v0.20.0 [output-discipline rules](../docs/output-discipline.md)
against the `code-reviewer` skill. It exists because the v0.19.0-and-earlier output of
the skill grew long, repetitive, and template-echoing — a pattern that buried real
blockers under empty section headers and "Confidence: high" / "Blocking: blocking"
boilerplate that contributed nothing the title did not already say.

## Setup

- Workspace: any non-trivial repo with a small open PR (3–6 changed files).
- Issue context: a Jira / GitHub issue is **available and reachable** so the run is
  fully issue-aware. (The unavailable-context case is covered by
  [`code-reviewer-unavailable-context`](./code-reviewer-unavailable-context.md).)
- Mode: `pr`.
- Findings expected: at least one `blocker`, one `major`, one `minor`, no `nit` (so
  the structured-noise problem is testable but the diff is small enough to score
  cleanly).

## Prompt

```text
Review this PR using the code-reviewer skill in PR mode.

Review target: <PR URL>
Base: <base branch>
Issue context: <issue URL>

Group findings by severity and finish with one verdict.
```

## Pass criteria

The agent's response **must**:

1. Render **only the sections of the Expected Output Contract that have content**.
   Sections with nothing to report are omitted entirely. The only required-even-if-empty
   section is the one-line `## Final Verdict`.
2. Render every finding in the **single-bullet form** documented in
   [`docs/output-discipline.md`](../docs/output-discipline.md#findings-format-code-reviewer-manual-tester-defects-investigator-hypotheses) —
   one bullet, severity-prefixed title, evidence + why + fix as inline sentences,
   confidence and blocking decision in parentheses. The seven-bullet
   `Severity: / Title: / Affected file: / Evidence: / Why it matters: / Suggested
   fix: / Confidence: / Blocking decision:` per-finding block is a **failure**.
3. Render `Review Limitations / Unavailable Context` as a **single line or short
   paragraph**, never a six-bullet placeholder where each item is `none`.
4. Render the verdict as **one line**: `<VERDICT> — <one-sentence reason>` with at
   most one follow-up line. Banners, blockquotes, ASCII rules, or "Status: ✅" are
   failures.
5. Not restate the user's prompt, the PR URL, or the ticket key as a paragraph
   before the result. The header line at the top is the only allowed echo.
6. Not include a "Workflow steps run" / "I will now do X" pre-amble.
7. For a PR of 3–6 changed files with ≤ 4 findings, fit comfortably on a phone screen
   (the v0.19.0 rendered output of the same kind of PR ran 100+ lines of mostly
   template; the v0.20.0 output of the same PR is expected to be ≤ 40 lines).

## Failure modes this eval catches

- **Template-echo failure.** Agent prints every contract section header even when
  empty (`Issue/Ticket Alignment Result`, `Engineering Quality Result`,
  `Findings Grouped By Severity`, `Review Limitations / Unavailable Context`,
  `Final Verdict`) with `none` placeholders underneath. **Fail.**
- **Per-finding skeleton failure.** Agent expands each finding into a seven-line
  sub-list (`- Severity:` / `- Title:` / `- Affected file:` / etc.) instead of one
  bullet. **Fail.**
- **Workflow-recap failure.** Agent narrates "I detected execution mode, then I
  fetched the issue, then I ran the requirement-understanding gate, then I ..."
  before the result. **Fail.**
- **Banner failure.** Agent wraps the verdict in `=====`, ASCII art, emoji
  status icons, or a markdown blockquote. **Fail.**

## Reference good-shape transcript

A passing transcript is captured at
[`eval-runs/v0.20.0/code-reviewer-concise-output.md`](../eval-runs/v0.20.0/code-reviewer-concise-output.md).

## Reference bad-shape transcript (anti-example)

The "verbose v0.19.0" output of the same kind of PR is captured for contrast in the
same eval-runs file. Reviewers running this eval against a new model release should
compare against both and confirm the new run looks like the **good** transcript, not
the bad one.

## Why this eval exists

The `code-reviewer` Expected Output Contract is a long YAML-ish skeleton because it
has to enumerate every section the agent **may** emit across all four review modes
(`inner`, `outer`, `pr`, `manual`). Without a counter-pressure rule, agents tend to
treat the skeleton as a checklist and dump every heading. Output discipline is what
turns the skeleton back into a menu.
