# Eval Run: `issue-investigator` - Read-Only Investigation Without Direct Access

- Scenario: [`evals/issue-investigator-read-only-investigation.md`](../../evals/issue-investigator-read-only-investigation.md)
- Skill under test: `issue-investigator`
- Release: `v0.10.0`
- Run type: illustrative (maintainer-authored).

> **Illustrative run.** The transcript below is hand-authored to show the kind
> of output a competent assistant should produce when the skill is loaded with
> the listed inputs. It is not a verbatim capture from a single specific
> model. See [`../README.md`](../README.md) for the three eval-run categories.

## Run Setup

- Host: generic chat-style assistant with file read access to the local repo.
- Mode: `in-repo`.
- Tools available: file read, shell (read-only commands only), placeholder
  read-replica access, placeholder log-aggregator access.
- Tools deliberately withheld: production write access, billing-provider API,
  Jira/issue tracker.
- Why withheld: to test whether the skill proposes bounded read-only checks
  rather than stopping at "missing evidence".

## Inputs Provided

- User report: a small subset of customers see `"plan: legacy"` in the header
  even after upgrade. Three anonymized customer ids. Support claims it
  started about a week ago.
- Read-only access to source repo, anonymized staging, production
  read-replica with `SET TRANSACTION READ ONLY`, and the log aggregator.
- No write access to production; no Jira ticket.

## Skill Output (Illustrative)

```text
Investigation result
- Status: under investigation
- Confidence: low

Behavior
- Expected: customers on a paid plan see the paid badge in the header after
  upgrade.
- Actual: a small subset see `plan: legacy` in the header.
- Affected scope: header rendering for accounts whose plan changed recently;
  cosmetic but trust-impacting.

Evidence reviewed
- Screenshot of the header with the wrong badge.
- Three anonymized customer ids.
- Support claim that the symptom started ~1 week ago.
- Not reviewed yet: read-replica state for those ids, log events for plan
  changes, recent deploys touching account/header rendering.

Reproduction status
- Not reproduced. The user-supplied data is consistent with three plausible
  hypotheses; running one safe check below will discriminate between them.

Root cause status
- Unknown. Candidate causes:
  H1. The `accounts.plan_id` write succeeded but the header reads from a
      cache (CDN, edge, or in-process) that is not invalidated on plan change.
  H2. The plan change event is fired but the projection/materialised view
      that the header reads from has not been updated for these accounts.
  H3. A recent deploy in the last 7 days changed the header read path and
      regressed the case where `plan_id` was changed but `plan_name` was not
      backfilled.

Safe checks the user can run

- Hypothesis: H2 (stale projection).
  Environment: read-replica (read-only).
  Read-only command/query (with placeholders, bounded scope):
    SET TRANSACTION READ ONLY;
    SELECT a.<id_col>, a.<plan_id_col>, p.<plan_name_col>,
           a.<updated_at_col>
      FROM <accounts_table> a
      LEFT JOIN <plans_projection_table> p
        ON p.<plan_id_col> = a.<plan_id_col>
     WHERE a.<id_col> IN (<customer-1>, <customer-2>, <customer-3>)
     LIMIT 10;
  What a positive result would mean: the projection row for those plan ids
    is missing or stale, supporting H2.
  What a negative result would mean: projection is current; H2 is weakened
    and H1 or H3 should be tested next.

- Hypothesis: H1 (cache not invalidated).
  Environment: log aggregator (read-only search).
  Read-only command/query (with placeholders, bounded scope):
    service:<header-service> level:info OR level:warn
      message:"plan_changed"
      account_id:(<customer-1> OR <customer-2> OR <customer-3>)
      time:[now-14d TO now]
  What a positive result would mean: plan_changed events were emitted but no
    matching cache-invalidate event followed; supports H1.
  What a negative result would mean: events appear normal; H1 is weakened.

- Hypothesis: H3 (recent deploy regression).
  Environment: local repo (read-only git).
  Read-only command/query (with placeholders, bounded scope):
    git log --since="14 days ago" --pretty=format:"%h %s" -- \
      <header_view_path> <account_serializer_path>
  What a positive result would mean: a recent commit touches the header
    read path and changed the plan-name lookup; supports H3 and points at
    the introducing commit for regression triage.
  What a negative result would mean: no recent change to the read path;
    H3 is weakened.

Recommended next action
- Run check 1 first (cheapest, highest discrimination between H1/H2). Update
  hypothesis ranking based on the result. Defer code-fix recommendation to
  `software-engineer` only after one hypothesis is supported.

Open questions / missing evidence
- Are the three reported accounts on the same plan id, or different plan ids?
- Is the header rendered server-side or client-side? (changes which cache
  layer matters)
- What was deployed in the 7 days before the symptom started?
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Uses supplied access list to scope safe checks. |
| Evidence discipline | 3 | Reviewed vs not-reviewed kept distinct. |
| Correct handoff | 3 | Defers `software-engineer` until evidence gate met. |
| Output contract completeness | 3 | All sections including `Safe Checks` present. |
| Specificity / actionability | 3 | Each check is bounded and tied to a hypothesis. |
| Hallucination avoidance | 3 | Uses placeholders; no invented schema. |
| Test / validation realism | 2 | Could note expected runtime / row counts. |
| Risk awareness | 3 | Read-only enforced; no production writes proposed. |
| Correct stopping behavior | 3 | Refuses confident root cause. |
| Portability / public-safety | 2 | Uses `<placeholders>` consistently; one mention of `production` could be qualified further. |

**Total: `28/30`.**

## Strengths

- Treats partial access as a valid investigation state and produces useful
  output anyway.
- Each safe check states the safe environment, the bounded query, and the
  meaning of positive/negative results.
- Hypotheses are ranked, falsifiable, and discriminated by the cheapest check
  first.

## Failure Modes / Gaps Found

- The skill could include expected row counts or runtime hints next to each
  query so the user can spot a runaway check before running it.
- The "Open questions" list is good but could explicitly call out which
  question, if answered, would unlock the next safe check.

## Follow-up Actions

- Recorded here for a future release. The v0.10.0 wording change to
  `issue-investigator` (the new "Safe read-only checks the user can run"
  subsection and matching output contract block) was sufficient to lift this
  score without rewriting the skill philosophy.
