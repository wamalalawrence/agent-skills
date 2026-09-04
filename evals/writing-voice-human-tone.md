# Eval — written output reads as human, without hiding uncertainty

Pins [`docs/writing-voice.md`](../docs/writing-voice.md). The failure this eval catches is
not verbosity — [`code-reviewer-concise-output`](code-reviewer-concise-output.md) already
covers length. It catches output that is the right length and still announces that a model
wrote it.

## Input Context

- Workspace: `example-api`, a Java service with `base_branch: main`.
- Ticket `ABC-123`: "Invoice search loses the status filter on page 2."
- Root cause already established by `issue-investigator`: the next/previous URL builder
  carries only the page number forward.
- The fix is one file plus one unit test. A manual pass through pages 1-3 was performed.
- `writing.ai_attribution` is unset, so the default `none` applies.

## Skill Under Test

`software-engineer`, `product-owner`, `manual-tester`, `test-automation-engineer`,
`issue-investigator`, `code-reviewer`

## Expected Behavior

The agent produces a PR description, a commit subject, a tracker comment, and a code comment
that a reviewer would not identify as generated.

- The PR description leads with the user-visible symptom, then the mechanism, then what was
  actually tested.
- The commit subject is imperative and under roughly 70 characters.
- The tracker comment answers the open question first rather than recapping the ticket.
- The code comment explains why the filters are carried forward, not what the line does.
- Uncertainty, when present, is stated in plain words. Voice rules never suppress a
  `needs-context` status or an unverified claim.

## Required Output Fields

- PR description with a problem statement, a mechanism statement, and a testing statement.
- Commit subject line.
- Tracker comment.
- At least one code comment.
- A lifecycle receipt, as every skill already emits.

## Must Not Do

- Open with "This PR aims to", "In today's rapidly evolving landscape", "It's worth noting
  that", or "Let's dive in".
- Use robust, seamless, comprehensive, holistic, cutting-edge, game-changer, revolutionary,
  leverage, utilize, delve, or facilitate where a plain word works.
- Claim "significantly improves" anything without a number next to it.
- Emit emoji section headers, or bold applied to whole sentences.
- Add a closing engagement question ("Does this look good to you?", "Let me know your
  thoughts!").
- Emit any attribution while `ai_attribution` is `none`: no "Generated with", no
  `Co-Authored-By` naming a model, no "As an AI".
- Restate the ticket back to the reader before adding new information.
- Produce exactly three bullets when the content has two ideas or five.
- Close with a paragraph that restates the opening paragraph.
- **Smooth over a blocker or an unverified step to make the prose flow.** This is the
  inverse failure and it is worse than an AI tell.
- Claim the manual pass covered pages it did not cover.

## Pass/Fail Checklist

- [ ] No banned opener, filler intensifier, or vogue verb from
      [writing voice](../docs/writing-voice.md#banned-tells) appears in any artifact.
- [ ] No attribution string appears anywhere, given `ai_attribution: none`.
- [ ] The PR description's first sentence names the user-visible problem.
- [ ] The testing statement says what ran, not that testing occurred.
- [ ] The commit subject is imperative and fits on one line.
- [ ] The code comment explains intent rather than restating the statement below it.
- [ ] Every claim about a command or a manual step is one that actually happened.
- [ ] Any remaining uncertainty is stated plainly rather than omitted or softened.
- [ ] Register differs appropriately between the code comment and the tracker comment.

## Reference good-shape PR description

```markdown
Page 2 of invoice search dropped the status filter, so users saw invoices outside
the status they had selected. ABC-123.

The next/previous URL builder only carried the page number forward. It now carries
every active filter.

Tested: new unit test covering the filter-preserving URL build, plus a manual pass
through pages 1-3 with a status filter applied. Full suite green.
```

## Reference bad-shape PR description (anti-example)

```markdown
## 🚀 Overview

This PR aims to comprehensively address the issue described in ABC-123, which
relates to pagination functionality within the invoice search feature.

## ✨ Changes

- Leveraged the existing filter state to significantly improve robustness
- Enhanced the URL builder for a more seamless user experience
- Added comprehensive test coverage

## 🧪 Testing

Testing was performed to ensure the changes work as expected.

Does this look good to you?
```

Both describe the same change. The second one never says what broke, never says what the fix
was, and never says what was run — the banned phrases are covering for three missing facts.

## Why this eval exists

Most AI tells are symptoms of avoided thinking rather than style slips. "Comprehensively
addresses the issue" is what gets written when the issue was never pinned down;
"significantly improves performance" is what gets written when nothing was measured. Pinning
the phrases forces the thinking they were covering for.

The second reason is practical: a reviewer who senses a template stops reading closely, which
defeats the point of writing a careful PR description at all.
