# Eval Runs

This directory holds **scored sample runs** of the skills in this repository
against the scenarios in [`evals/`](../evals/). Each run records what was given
to the skill, what the skill produced, how the output scored against the
[skill quality scorecard](../docs/skill-quality-scorecard.md), and what the
maintainer changed (or chose not to change) as a result.

Eval runs are organized by release. Start with the most recent summary:

- [`v0.11.0/summary.md`](v0.11.0/summary.md)
- [`v0.10.0/summary.md`](v0.10.0/summary.md)
- [`v0.9.0/summary.md`](v0.9.0/summary.md)

## Purpose

The repository already ships:

- skill definitions with output contracts and guardrails,
- eval scenarios that describe expected behavior,
- a maintainer scorecard, and
- a structural validator.

Eval runs add a missing piece: visible evidence of how the skills actually
behave on realistic inputs, including where they still fail or feel weak.

This is intentionally a manual, lightweight practice. It is not a benchmark and
not a CI gate. The goal is to make skill quality reviewable by a human reader,
not to prove correctness with a number.

## What An Eval Run Is

Each per-skill eval-run file contains:

- a pointer to the scenario in [`evals/`](../evals/),
- the skill under test and the release being reviewed,
- the run setup: agent host, mode (`local-workspace` or `in-repo`), tools
  available, and what was deliberately withheld,
- the input context provided to the skill,
- the skill output captured during the run,
- a per-criterion score against the
  [skill quality scorecard](../docs/skill-quality-scorecard.md),
- strengths, failure modes, and follow-up actions.

## What An Eval Run Is Not

- Not a benchmark and not a leaderboard.
- Not a guarantee that a future model run will behave the same way.
- Not a replacement for human review of code, fixes, or releases.
- Not proof that the skill is correct in any specific business context.

## How These Were Produced

Each eval-run file must declare which of these three categories it belongs to.
The category appears at the top of the file and in the run-setup block.

### 1. Illustrative (maintainer-authored)

The maintainer writes the kind of output a competent assistant should produce
when the skill is loaded with the listed inputs. The transcript is hand-written
to make scoring, strengths, and gaps visible. It is **not** a real model run.

- Use when: the gap being demonstrated is structural (output contract, stopping
  behavior, handoff routing) and a real run would not change the conclusion.
- Required label in the file: `Run type: illustrative (maintainer-authored).`
- Required disclaimer in the file: a short paragraph stating that the
  transcript is hand-authored and not a verbatim model capture.
- Required: list the inputs, the deliberately withheld tools/context, and the
  scoring rationale. The reader should be able to reproduce the same scoring
  exercise on a real run.

### 2. Real model transcript

The transcript is captured verbatim from a single specific assistant on a
single date. The model identifier, host, and date are recorded. Light editing
is allowed only for redaction (no real customer data, secrets, hostnames, or
tickets) and for trimming irrelevant pleasantries; both must be disclosed.

- Use when: the eval needs to show actual model behavior under realistic
  incomplete context, not the maintainer's idealized output.
- Required label in the file: `Run type: real model transcript.`
- Required fields in the run-setup block: assistant host, model identifier,
  date, mode (`local-workspace` or `in-repo`), tools available, tools
  withheld, redactions made.
- Real model transcripts are still scored against the same scorecard. They are
  not endorsements of any specific model.

### 3. Future automated evals (placeholder category)

This category is reserved for future releases. It would cover programmatically
captured outputs, structured comparison against the output contract, and
machine-readable scoring. Nothing in this repository is in this category yet.

- Required label when added: `Run type: automated.`
- Until automated evals exist, this section documents the intent so the
  category is not silently conflated with "illustrative" or "real model".
- Automated evals, if added, will not gate CI. They are a maintainer review
  aid, not a benchmark.

### Choosing a category

A v0.10.0+ release that ships any new eval-run file must explicitly pick one
of the three categories above. Unlabeled runs are not allowed.

The runs in `eval-runs/v0.9.0/` are all category 1 (illustrative). They are
labeled accordingly. Going forward, releases should mix in real model
transcripts where they add evidence value beyond the illustrative ones.

## Public-Safety Rules

- No real customer data, private tickets, secrets, hostnames, or local paths.
- No hardcoded company workflows. Eval runs use generic systems and placeholder
  identifiers.
- No claim that the skill is "validated" or "certified" for any production
  context.

## How To Add A New Eval Run

1. Pick or add a scenario file in [`evals/`](../evals/).
2. Pick the category: illustrative, real model transcript, or (future)
   automated. Label the file accordingly.
3. Run the skill under realistic conditions, or write the illustrative output
   that demonstrates the behavior under review. Capture the input context and
   the skill output.
4. Score each scorecard criterion `0`-`3` with a short justification.
5. Record strengths, failure modes, and any follow-up edits to the skill.
6. Add the file under `eval-runs/<release>/` and link it from the release
   summary.
