# Eval Run — v0.20.0

## Scenarios captured

- [`code-reviewer-concise-output`](./code-reviewer-concise-output.md) — the
  template-echo / verbose-output regression that motivated this release. Captures
  the **bad** v0.19.0-shape transcript next to the **good** v0.20.0-shape
  transcript on the same kind of PR.
- [`model-routing-removal`](./model-routing-removal.md) — pins the removal of
  `CODE_REVIEWER_MODEL` / `code_reviewer_model` from the public surface and
  documents why no replacement was added.

## Headline result

The `code-reviewer` skill now produces output that fits a phone screen for small
PRs (≤ 4 findings) and at most two screens for ≤ 10 findings, instead of the
v0.19.0 ~100-line template-echo dump that contained large blocks of
`Severity: / Title: / Affected file: / Evidence: / Why it matters: / Suggested
fix: / Confidence: / Blocking decision:` per finding.

The shape is enforced two ways:

1. **In the spec** — every `SKILL.md` Expected Output Contract now links to
   [`docs/output-discipline.md`](../../docs/output-discipline.md) and restates the
   `Omit empty sections` rule inline. The new `## Output Style (binding)` block
   explicitly forbids the seven-line per-finding skeleton, the workflow recap,
   and the template echo.
2. **In the validator** — `scripts/validate-repo.py` adds
   `check_skill_output_discipline` to refuse any new `SKILL.md` that drops the
   link or the rule, and `check_no_code_reviewer_model` to refuse any
   reintroduction of the removed model knob outside the changelog and these
   eval-run notes.

## Verdict

PASS_WITH_NOTES — the spec changes and validator gates landed; the actual
agent-side conciseness is still measured per-host because output discipline
ultimately depends on the model rendering the contract. The scenario file lists
the failure modes a reviewer should look for when re-running this eval against a
new model release.

## Not in scope

- No change to the underlying review **logic** (severity rubric, requirement-
  understanding gate, devil's-advocate paragraph, evidence-pack handoff). The
  v0.20.0 release is a *presentation* fix.
- No change to the destructive-action safety floor or the iteration-convergence
  rule.
