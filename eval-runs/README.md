# Eval Runs

This directory holds **scored sample runs** of the skills in this repository
against the scenarios in [`evals/`](../evals/). Each run records what was given
to the skill, what the skill produced, how the output scored against the
[skill quality scorecard](../docs/skill-quality-scorecard.md), and what the
maintainer changed (or chose not to change) as a result.

Eval runs are organized by release. Start with the most recent summary:

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

The runs in this directory are **illustrative**. They represent the kind of
output a competent assistant should produce when the skill is loaded with the
listed inputs, and they were authored by the maintainer to make scoring,
strengths, and gaps visible. They are clearly labeled in each file. They are
not raw transcripts captured from a single specific model.

Future releases may include genuinely captured outputs. When that happens, the
eval-run file should record the host, model identifier, date, and any
post-processing.

## Public-Safety Rules

- No real customer data, private tickets, secrets, hostnames, or local paths.
- No hardcoded company workflows. Eval runs use generic systems and placeholder
  identifiers.
- No claim that the skill is "validated" or "certified" for any production
  context.

## How To Add A New Eval Run

1. Pick or add a scenario file in [`evals/`](../evals/).
2. Run the skill under realistic conditions. Capture the input context and the
   skill output.
3. Score each scorecard criterion `0`-`3` with a short justification.
4. Record strengths, failure modes, and any follow-up edits to the skill.
5. Add the file under `eval-runs/<release>/` and link it from the release
   summary.
