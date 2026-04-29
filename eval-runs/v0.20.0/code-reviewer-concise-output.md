# Eval Run — code-reviewer concise output (v0.20.0)

Pins the [`code-reviewer-concise-output`](../../evals/code-reviewer-concise-output.md)
scenario against the v0.20.0 spec.

## Setup recreated

- Target: a 5-file PR with ≈ +48 / −6 lines, one `blocker`, two `major`, two
  `minor` findings (mirrors the real-world PR that motivated this release).
- Mode: `pr`.
- Issue context: reachable Jira issue.

## Bad-shape transcript (v0.19.0 spec, kept for contrast)

The v0.19.0 contract was a long YAML-style skeleton. Without an output-discipline
counter-pressure rule, agents tended to render every section heading even when
empty, expand each finding into a seven-line sub-list, narrate the workflow they
ran, and wrap the verdict in banners. The result on the same PR ran ~150 lines
of mostly template noise, with the actual blockers buried under repeated
`- Severity: blocker` / `- Title: ...` / `- Affected file/area: ...` /
`- Evidence: ...` / `- Why it matters: ...` / `- Suggested fix: ...` /
`- Confidence: high` / `- Blocking/advisory decision: blocking` blocks.

That shape is the **failure mode** this release exists to prevent. It is
captured here for regression contrast — re-runs against new model releases
should never produce a transcript that looks like it.

## Good-shape transcript (v0.20.0 spec)

Same PR, same model, same prompt — rendered against the tightened contract:

```markdown
## Code Review — cumo-bpf @ bugfix/BPF-780-Error-in-Banking-file-exchange-and-statement-processing

- Mode: pr · Issue awareness: issue-aware
- Base: develop · Files reviewed: 5/5
- Standards used: repo conventions (BPF-768 EAGER-fetch finding) + JPA defaults

## Issue/Ticket Alignment

- BPF-780 lists TS-04 (Bulk payment sessions) and TS-05 (Banking file exchange)
  as inconsistent on RMVQA. The diff plausibly addresses TS-05 (NPE guard around
  null `paymentCreditFileDir`) but does not touch any TS-04 path.
- Alignment verdict: partially aligned.

## Findings

- **blocker: PaymentOrder.account / PaymentOrder.service silently flipped from
  LAZY to default EAGER** — `@ManyToOne(fetch = LAZY)` removed on both fields;
  JPA default is EAGER. Why it matters: PaymentOrder is hot; this re-introduces
  the exact regression BPF-768 was merged to remove, and the sibling
  `serviceRegisteredPD` keeps a "do not make EAGER" comment, suggesting the
  change is unintentional. Fix: revert both to `fetch = LAZY`. (confidence: high;
  blocking)
- **major: Commented-out test fixture shipped in production `main()`** —
  `// Uncomment createDefaultKvpFolders() only in case of manual testing with
  SoapUI` plus a fully-implemented helper that overwrites `kvpHome` with a temp
  dir. Why it matters: a one-line uncomment activates production startup that
  destroys real EBICS folder paths. Fix: move into a `local-soapui` profile or
  delete from `src/main`. (confidence: high; blocking)
- **major: Bug fix lands without a regression test** — no test pins the new
  null-`paymentCreditFileDir` branch. Why it matters: silent regression
  (returns empty list); easily reintroduced. Fix: add a test mocking
  `BankConnection#getPaymentCreditDir() == null`. (confidence: high; blocking)
- **major: TS-04 part of the ticket not addressed** — diff touches no
  bulk-payment-session code. Why it matters: closing BPF-780 with this PR marks
  TS-04 fixed without code change behind it. Fix: split the ticket or include the
  TS-04 fix. (confidence: medium; blocking)
- **minor: Non-actionable log message "Check please why."** — describe state
  instead. Fix: `"No payment credit directory configured for service [{}]; ..."`.
  (confidence: high; advisory)

## Devil's-Advocate Self-Rebuttal

The author may have measured EAGER as a net win because account/service are
accessed on every PaymentOrder load. Even if true, the change is unrelated to
BPF-780, undocumented, untested, and contradicts the explicit "do not make
EAGER" comment kept on the very next field. Verdict stands.

## Review Limitations

BPF-780 has no comments and the PR body is empty — the diff → TS-05 mapping is
inferred, not read from a failure log; CI was not re-run locally.

## Final Verdict

REQUEST_CHANGES — silent EAGER conversion, dead "uncomment-to-activate" code in
`main()`, and missing TS-04 coverage make this unsafe to merge as-is.
Follow-up: revert PaymentOrder fetch changes, move/delete `createDefaultKvpFolders`,
add the null-`paymentCreditFileDir` test, document the TS-04 status before close.
```

## Pass-criteria scoring

- ✅ Empty sections omitted (`Engineering Quality` collapsed into the findings
  themselves; `Review Limitations` rendered as one paragraph instead of a
  six-bullet `none` block).
- ✅ Every finding is one bullet using the
  [Output Discipline finding format](../../docs/output-discipline.md#findings-format-code-reviewer-manual-tester-defects-investigator-hypotheses).
- ✅ No workflow recap before the result.
- ✅ No banners or status decorations around the verdict.
- ✅ Total length ≈ 50 lines for 5 findings — fits two phone screens.

Pass.

## How to re-run

1. Copy the prompt block from
   [`evals/code-reviewer-concise-output.md`](../../evals/code-reviewer-concise-output.md)
   against any small PR with reachable issue context.
2. Compare the rendered output against the **good-shape transcript** above and
   the **bad-shape pattern** described in
   [`docs/output-discipline.md`](../../docs/output-discipline.md).
3. Score each pass-criterion in the eval scenario file. A single `❌` is a
   fail — the spec was loaded but the model ignored it, which is itself a
   reportable regression in the host's instruction-following.
