# Eval Run: `code-reviewer` - Review With Significant Unavailable Context

- Scenario: [`evals/code-reviewer-unavailable-context.md`](../../evals/code-reviewer-unavailable-context.md)
- Skill under test: `code-reviewer`
- Release: `v0.10.0`
- Run type: illustrative (maintainer-authored).

> **Illustrative run.** The transcript below is hand-authored to show the kind
> of output a competent assistant should produce when the skill is loaded with
> the listed inputs. It is not a verbatim capture from a single specific
> model. See [`../README.md`](../README.md) for the three eval-run categories.

## Run Setup

- Host: generic chat-style assistant with file read access to the local repo.
- Mode: `in-repo`.
- Tools available: file read, diff inspection, PR title/description/comments.
- Tools deliberately withheld: linked issue tracker, CI artifacts,
  acceptance criteria, architecture guideline document, runtime logs/metrics.
- Why withheld: to test whether the skill records review limitations rather
  than papering over them with a confident `PASS`.

## Inputs Provided

- A diff (~220 lines, 4 files) changing cache-eviction logic in a
  notification fan-out service.
- PR title, PR description ("fixes flakiness in notification delivery"),
  3 inline review comments.
- Base branch.
- A linked issue id `<ISSUE-KEY>` referenced in the PR description, but the
  issue tracker is unreachable.

## Skill Output (Illustrative)

```text
Code Review - <repo> @ <branch>
- Review scope: PR diff (~220 lines, 4 files)
- Review mode: pr
- Issue awareness: partially issue-aware (issue id present, content not read)
- Base: <base-branch>
- Files reviewed: 4/4
- Standards used: PR description; architecture guideline referenced but not
  supplied

Issue/Ticket Alignment Result
- Issue summary: not available (linked issue could not be read).
- Expected behavior: inferred from PR description ("fix flakiness in
  notification delivery"); inference only, not authoritative.
- Acceptance criteria mapping: not available.
- Alignment verdict: unclear.

Engineering Quality Result
- Correctness: cache-eviction now triggers on both publish-success and
  publish-retry paths; one branch (publish-failure with retry-exhausted)
  appears to skip eviction. Worth confirming this is intentional.
- Tests: PR adds two unit tests around the eviction call; no integration test
  covers the failure-with-retry-exhausted path.
- Security: no auth or PII surface touched.
- Performance: eviction is O(1) per message; not a concern.
- Observability: an existing structured log line is preserved; no new metric
  for eviction-skipped cases.
- Compatibility / regression risk: previous flakiness was reportedly caused
  by stale entries surviving a retry; the new logic plausibly fixes that, but
  without the linked issue or CI evidence the claim cannot be verified.

Findings Grouped By Severity

### major: Eviction may be skipped on retry-exhausted failure
- Severity: major
- Affected file/area: <cache_eviction_path>
- Evidence: in the diff, the `on_publish_failure` branch returns before the
  call to `evict(...)` when retry budget is exhausted. The success and
  retry branches both call `evict(...)`. Comment in the diff says "drop the
  message" but does not address the cache entry.
- Why it matters: stale cache entries surviving a terminal failure could
  reproduce the flakiness this PR aims to fix.
- Suggested fix: either evict on retry-exhausted as well, or document why
  retaining the entry is intentional.
- Confidence: medium
- Blocking/advisory decision: blocking pending engineer response.

### minor: No coverage for retry-exhausted path
- Severity: minor
- Affected file/area: <test_file>
- Evidence: the two new unit tests cover success and retry; no test covers
  the retry-exhausted branch identified above.
- Why it matters: the path most likely to regress under the original
  flakiness is unverified.
- Suggested fix: add a unit test for `on_publish_failure` with retry budget
  exhausted.
- Confidence: high
- Blocking/advisory decision: advisory.

Review Limitations / Unavailable Context
- Issue context not accessed: linked issue `<ISSUE-KEY>` was unreachable;
  expected behavior was inferred from the PR description only.
- Code paths not inspected: vendored notification client (binary); skipped
  intentionally.
- Tests / builds / CI not executed or not observed: CI artifacts could not
  be fetched; "tests passed" was reported in PR comments but not verified
  here.
- Standards / guidelines referenced but not supplied: architecture guideline
  referenced in PR description was not provided; alignment with it could not
  be checked.
- Runtime / deployment / observability evidence not available: no logs,
  metrics, or feature-flag state inspected.
- Effect on confidence: alignment verdict is `unclear` and the verdict
  cannot be a bare `PASS` while the linked issue and CI evidence are missing.

Final Verdict
- Verdict: PASS_WITH_NOTES
- Reason: Engineering-quality findings are addressable, but issue alignment
  and CI verification are missing. The retry-exhausted finding should be
  resolved before merge.
- Follow-up needed: provide the linked issue contents, the architecture
  guideline, and the failing-regression-test commit (or a summary of the
  flakiness reproduction). Re-run the review once those are available.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Reads PR fields; flags issue access gap. |
| Evidence discipline | 3 | Review Limitations section is concrete. |
| Correct handoff | 2 | Could route the missing-issue gap to `issue-investigator`. |
| Output contract completeness | 3 | All sections including Review Limitations present. |
| Specificity / actionability | 3 | Findings cite file area and concrete fix. |
| Hallucination avoidance | 3 | Does not invent issue contents or CI results. |
| Test / validation realism | 2 | Names the missing test path; could include test code shape. |
| Risk awareness | 3 | Identifies retry-exhausted regression risk. |
| Correct stopping behavior | 3 | Verdict is `PASS_WITH_NOTES`, not `PASS`. |
| Portability / public-safety | 2 | Uses placeholders consistently; one path could be more generic. |

**Total: `27/30`.**

## Strengths

- The Review Limitations section is concrete and tied to the verdict.
- The verdict refuses a bare `PASS` while context is missing, exactly as the
  v0.10.0 wording change intended.
- Findings cite evidence visible in the diff and do not invent the
  unreachable issue's contents.

## Failure Modes / Gaps Found

- The skill could explicitly recommend invoking `issue-investigator` to
  produce the missing issue context rather than only listing the gap.
- The "Effect on confidence" line is correct but could quantify how the
  verdict would change if the missing context were supplied.

## Follow-up Actions

- Recorded here for a future release. The v0.10.0 wording change (the new
  workflow step "Record review limitations explicitly" plus the
  `Review Limitations / Unavailable Context` output section) was sufficient
  to lift this score without rewriting the skill philosophy.
