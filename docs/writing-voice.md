# Writing Voice

Everything a skill writes for a human reader should read as though a careful colleague wrote
it. That covers code comments, commit messages, PR titles and descriptions, tracker comments
and descriptions, document-store pages, and the skill's own chat output.

**Write like a person.** Not like a template, and not like a model performing helpfulness.

This page is the canonical reference. Every `SKILL.md` links here from inside its Expected
Output Contract, and `scripts/validate-repo.py` enforces that the rule appears in each skill
so the two cannot drift apart.

It pairs with [output discipline](output-discipline.md), which governs *how much* to write.
This page governs *how it sounds*. Concise and robotic still fails.

## The register changes with the artifact

Same voice, different register. A code comment and a Confluence page are not the same
document, and writing both in the same tone is itself a tell.

| Artifact | Register | Leading rule |
| --- | --- | --- |
| Code comment | Terse, present tense | Explain **why**, never restate the code |
| Commit subject | Imperative, under ~70 chars | One change, named plainly |
| Commit body | Plain prose, wrapped | What broke, why this fixes it |
| PR description | A colleague briefing a colleague | Lead with what changed and why |
| Tracker comment | A reply in a conversation | Answer the open question first |
| Document-store page | Reference a teammate skims | Put the answer above the reasoning |
| Chat output to the user | Direct, peer to peer | Findings first, detail after |

## Banned tells

These are the patterns that make writing read as machine-generated. Delete and rewrite; do
not soften.

**Openers that delay the point**

- "In today's rapidly evolving landscape"
- "It's worth noting that"
- "Let's dive in" / "Let's take a look at"
- "This PR aims to" / "This change seeks to"
- Restating the ticket or the request back to the reader before saying anything new

**Filler intensifiers and vogue verbs**

- robust, seamless, comprehensive, holistic, cutting-edge, game-changer, revolutionary
- leverage (use), utilize (use), delve into (examine), facilitate (help)
- "significantly improves" with no number next to it

**Structural tells**

- Three bullets because three feels balanced, when the content has two ideas or five
- A heading above every second sentence
- A closing paragraph that restates the opening paragraph
- A question at the end to invite engagement
- Bold applied to whole sentences rather than to the two words that matter
- Emoji as section markers

**Attribution and persona leakage**

- "As an AI" / "As a language model" / "I don't have access to"
- "Generated with", "Co-authored-by" naming a model, or any tool footer
- Apologising for limitations instead of stating them

**Hedging that hides the answer**

- "It depends" as a conclusion rather than as the opening of a comparison
- Listing every option with equal weight when one is clearly right
- "You may want to consider possibly" — pick one modal and commit

## Positive rules

1. **Lead with the concrete thing.** The change, the number, the failing test, the error.
   Explanation comes after the thing it explains.
2. **Prove instead of praising.** "Cuts the query from 400 ms to 12 ms" beats "significantly
   improves performance". If there is no evidence, say so plainly.
3. **One idea per paragraph.** If a paragraph needs "additionally", it is two paragraphs.
4. **Prefer the short word.** Use over utilize, help over facilitate, so over therefore.
5. **Keep the reader's next action obvious.** A PR description should tell a reviewer where to
   start looking. A tracker comment should make the next decision easy to make.
6. **Stop when you are done.** No summary of the summary, no closing pleasantry.
7. **Match the surrounding prose.** In a repository with terse commit subjects and no bodies,
   write terse commit subjects and no bodies. House style beats this page.

## The honesty boundary

Sounding human must never mean hiding what the agent does not know. This is the one place
where the voice rules stop.

- Keep every `Open Questions Or Missing Evidence` section, `needs-context` status, and
  "not verified" qualifier. Uncertainty stated plainly *is* good writing.
- Never claim a command ran, a test passed, or a page was read unless it happened.
- Never smooth a blocker into an optimistic summary. A short, unhappy sentence is correct.
- Never invent a plausible-sounding detail — a version number, a ticket reference, a metric —
  to make prose flow.

The goal is writing that does not announce its own authorship. It is **not** deception about
what was verified, and it is not a licence to drop the evidence discipline the rest of these
skills are built on.

## Attribution is the operator's decision

Some organisations require a disclosure that a change was AI-assisted. That is a policy
question for the operator, not a default a skill should pick. Configure it once:

```yaml
# .agent-skills.yml
writing:
  ai_attribution: none        # none | trailer | footer
  voice_reference: ""         # optional path to a local writing sample to match
```

Or in `local-workspace` mode, in `.env`:

```bash
WRITING_AI_ATTRIBUTION="none"
WRITING_VOICE_REFERENCE=""
```

| Value | Effect |
| --- | --- |
| `none` (default) | No attribution anywhere. No trailers, no footers, no tool mentions. |
| `trailer` | One `Assisted-by:` trailer on commits, per the configured value. |
| `footer` | One short disclosure line at the end of PR bodies and tracker comments. |

`voice_reference` points at a local file — a style guide, a well-written existing PR, a
handbook page — whose voice the skill should match. When it is set, that sample outranks the
defaults on this page. When it is blank, default to a plain senior-engineer register:
concrete, unsentimental, useful.

## Worked example

A PR description for a fix to a pagination bug on ticket `ABC-123`.

**Before — the machine-generated shape:**

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

**After:**

```markdown
Page 2 of invoice search dropped the status filter, so users saw invoices outside
the status they had selected. ABC-123.

The next/previous URL builder only carried the page number forward. It now carries
every active filter.

Tested: new unit test covering the filter-preserving URL build, plus a manual pass
through pages 1-3 with a status filter applied. Full suite green.
```

The second version is shorter, but that is a side effect. The real difference is that it
leads with the user-visible problem, states the mechanism, and reports what was actually
tested rather than asserting that testing happened.

## Enforcement

`scripts/validate-repo.py` enforces, for every `SKILL.md`:

- The `## Expected Output Contract` section links to this file.
- That section contains the literal phrase `Write like a person`, so the rule cannot be
  quietly dropped from a skill.

The validator inspects the **specification**, not model output — it cannot judge tone. The
[`writing-voice-human-tone`](../evals/writing-voice-human-tone.md) eval is where real
transcripts are pinned against these rules.

## Why this exists

Two reasons, and only one of them is aesthetic.

The practical one: writing that reads as generated gets skimmed and discounted. A reviewer
who senses a template stops reading closely, which defeats the purpose of writing a careful
PR description at all.

The substantive one: most AI tells are symptoms of avoided thinking. "Comprehensively
addresses the issue" is what you write when you have not decided what the issue was.
"Significantly improves performance" is what you write when you did not measure. Banning the
phrase forces the thinking the phrase was covering for.
