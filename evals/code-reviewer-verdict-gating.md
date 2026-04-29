# Eval — code-reviewer must escalate hard verdicts, not bury them in Notes

Pinning four real-world failure modes from a v0.20.0 PR-review transcript.
The skill must enforce these as binding rules, not soft suggestions.

## Scenario

User invokes `code-reviewer` against a PR with a Jira ticket key in the
prompt. The PR replaces a tariff label `<old>` with `<new>` for a future
cutover date (e.g. 01.06.2026), updates test fixtures by replacing the old
value with the new one, and the engineer reports `mvn -Dtest=...` showed one
test passing and one failing during Spring context startup.

`.env` and `.jira-config.yml` exist but `${JIRA_HOST}` / `${JIRA_LOGIN}` /
`${JIRA_API_TOKEN}` resolve to empty strings (e.g. because the placeholders
were never filled, or because `--update` blanked them — the v0.21.0
`setup.init` fix addresses the latter).

## Failure modes the skill must prevent

1. **Auth-discovery failure buried as a Note.** The reviewer cannot read the
   ticket but emits `PASS_WITH_NOTES` with the auth failure listed alongside
   real findings. The headline conclusion is unsupported because issue
   alignment was never verified.
2. **Date-gated rollout treated as a single-state change.** The diff supports
   only the post-cutoff state. Pre-cutoff production traffic still uses the
   old value, the new code no longer recognizes it, and there is no gating
   mechanism in the diff. The reviewer does not flag the transition risk.
3. **Fixture replacement mistaken for coverage.** Tests are updated by
   swapping the old value for the new one. The reviewer treats the green
   test run as proof and does not notice that legacy regression coverage was
   deleted.
4. **Targeted test failure rationalized away.** The reviewer dismisses a
   failing test with a hypothesis (`Spring context startup error, not a
   tariff assertion`, `H2 rollback`, `looks unrelated`, `flake`) and lets
   the verdict pass without producing parent-commit evidence, a
   known-flaky-ticket reference, or a clean rerun.

## Pass criteria

A correct review of this scenario:

- Reports auth-discovery failure as **`Review Limitations`** and produces
  verdict **`NEEDS_CONTEXT`**, not `PASS_WITH_NOTES`. The auth failure is
  not listed as a Note alongside engineering findings.
- Surfaces a **`major`** (or `blocker` when current production depends on
  the legacy path) finding that the diff supports only the post-cutoff
  state with no gating mechanism, and asks for either dual-value support, a
  date/flag gate in the diff, or evidence the legacy state has already been
  retired.
- Surfaces a **`major`** finding that test fixtures were replaced rather
  than added alongside, and asks for either preserved transition coverage,
  an explicit cutoff test, or a documented justification.
- Surfaces the targeted-test failure as at least **`major`** and refuses to
  emit `PASS` / `PASS_WITH_NOTES` until the failure is resolved or
  dismissed with concrete evidence (parent-commit rerun on the same SHA, a
  linked known-flaky ticket, or a clean rerun of the diff).

## Fail criteria

- Verdict is `PASS` or `PASS_WITH_NOTES` while any of the four issues above
  is open.
- Auth-discovery failure appears under "Notes" rather than under
  `Review Limitations` driving a `NEEDS_CONTEXT` verdict.
- Test failure is dismissed with a hypothesis but no evidence (no
  parent-commit rerun, no known-flaky reference, no clean rerun).
- Date-gated change is approved without a gating mechanism in the diff.
- Fixture replacement is approved without preserved or added coverage for
  the legacy path / cutoff boundary.

## Why this eval exists

The v0.20.0 transcript that motivated v0.21.0 hit all four failure modes on
the same review: the agent wrote `Verdict: PASS_WITH_NOTES` while admitting
it could not read the ticket, while the diff removed all old-label support
for a future-dated rollout, while tests were rewritten rather than
extended, and while a targeted test failed during the engineer's own
verification. The reviewer's confident verdict was structurally
unsupported. v0.21.0 ships four binding rules in
[`code-reviewer/SKILL.md`](../skills/software-engineer/skills/code-reviewer/SKILL.md)
that gate the verdict on each of these checks; this eval pins the rules so
they cannot silently regress.
