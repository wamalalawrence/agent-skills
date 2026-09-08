# Automation Backlog, Test Levels, And Traceability

The reference for the three decisions that shape a suite over time: what to automate, at which
level, and how anyone later works out why a given test exists.

## Part 1 — Dispositions

Given a set of candidates — manual scenarios, acceptance criteria, a risk inventory, or the
existing suite itself — each one gets exactly one disposition.

| Disposition | Means |
| --- | --- |
| `AUTOMATE_NOW` | High value, stable behaviour, affordable to build and to keep |
| `AUTOMATE_LATER` | Worth automating, but blocked on stability, data, environment, or a dependency |
| `KEEP_MANUAL` | Real value, but exploratory, subjective, or too unstable to assert mechanically |
| `MOVE_TO_LOWER_LEVEL` | Already covered, or coverable, more cheaply below where it sits today |
| `REFACTOR_EXISTING` | The coverage exists but is brittle, slow, or unreadable |
| `REMOVE_DUPLICATE` | Another check already asserts the same behaviour |
| `OBSOLETE` | The behaviour it protects no longer exists |
| `NEEDS_CLARIFICATION` | Expected behaviour is not established, so nothing can be asserted yet |

`NEEDS_CLARIFICATION` is a real answer, not a placeholder. Automating an unclear scenario produces
a confidently green build for a system nobody agreed on, which is worse than no coverage.

## Part 2 — Deciding a disposition

Weigh these factors. Use ordinal judgements — `high` / `medium` / `low`, or `yes` / `no` — and say
which ones drove the call.

**Raises the case for automating**

- Business criticality: revenue, safety, compliance, or data integrity depends on it.
- Regression risk: the area changes often, or has broken before.
- Defect history: this behaviour has produced real incidents.
- Execution frequency: it would run on every PR or every release.
- Determinism: same input, same observable outcome, every time.
- Observability: there is a stable thing to assert on — an API response, a state change, a
  labelled element.
- Security or compliance relevance: the check is evidence someone will ask for.
- User impact: failure is visible to customers rather than cosmetic.

**Lowers it**

- Implementation cost: the scenario needs infrastructure that does not exist yet.
- Maintenance cost: it will break on every unrelated UI or schema change.
- Runtime cost: minutes added to every PR for a rarely-failing check.
- Data and environment complexity: bespoke setup, shared state, third-party dependencies.
- Existing lower-level coverage: the same logic is already asserted in a unit test.
- Subjectivity: the outcome is a judgement — layout, tone, "feels slow".

Do not invent a numeric score. A weighted `87/100` reads as measurement when it is arithmetic
performed on opinions. Score only when the repository already uses a scoring model, and then use
theirs. A short ordered list with a one-line reason per item is more useful and more honest.

Present a backlog as a table, ordered by disposition then by value, each row carrying its reason:

| Scenario | Disposition | Level | Reason |
| --- | --- | --- | --- |
| Checkout with an expired card | `AUTOMATE_NOW` | API | Revenue path, deterministic, already has an endpoint to assert |
| Invoice PDF looks right | `KEEP_MANUAL` | — | Subjective layout judgement; no stable assertion |
| Password rules on the signup form | `MOVE_TO_LOWER_LEVEL` | Unit | Pure validation logic; the e2e check adds 40s and no confidence |

## Part 3 — Test-level optimisation

Pyramid thinking is a heuristic about cost and feedback, not a ratio to hit. Optimise for the most
useful confidence at an acceptable runtime and maintenance cost, given this architecture and this
risk profile.

What to look for in an existing suite:

- **e2e checks that are really unit checks.** Validation rules, formatting, calculations, and
  branching logic asserted through a browser. Move them down; keep one path that proves the wiring.
- **Assertions duplicated across levels.** The same rule verified in a unit test, an API test, and
  an e2e test. Keep the lowest one, plus at most one integration path.
- **Missing contract coverage.** Producer and consumer both tested in isolation with no contract
  between them, so the pair breaks only in e2e — expensively and late.
- **Expensive setup repeated per test.** Logging in through the UI for a check the API could
  arrange in a second.
- **UI coverage adding little.** A browser test whose only unique assertion is that a page renders.
- **Gaps where e2e is genuinely required.** Cross-service workflows, real authentication, browser
  or device behaviour, and anything whose failure mode is the integration itself. These stay.

State the expected effect before and the measured effect after: which checks moved, what runtime
changed, and what confidence was deliberately given up.

## Part 4 — Traceability and the coverage map

Traceability answers one question: **why does this test exist, and what stops being protected if
it is removed?** A suite that cannot answer it accumulates tests nobody dares delete.

```text
requirement / acceptance criterion / defect
                    |
                    v
              test scenario
                    |
                    v
            automated check(s)
                    |
                    v
           execution / CI evidence
```

Preserve the identifiers that already exist — the ticket, the acceptance criterion, the manual
scenario id, the defect or reproduction recipe, the test-management case — and choose a mechanism
the repository already uses:

- Test metadata or annotations, when the framework supports them.
- Tags and groups, which double as suite selectors.
- Descriptive test names that state the behaviour rather than the mechanics.
- Reporting annotations that surface the link in the CI report.
- The persisted coverage map in the evidence pack.
- Test-management integration, where the project has one.
- A concise comment — for a defect-derived regression test, the investigation result and the
  introducing commit genuinely belong in the docstring.

Do not scatter ticket ids through production test code as noise. One authoritative link per test,
in the mechanism the repository already reads, beats the same key repeated in five places.

The coverage map is where this is persisted for the next agent. Keep it small: one row per
behaviour, its level, its automated check, and its source. It is what makes "what would break if
we deleted this" answerable without reading the whole suite.
