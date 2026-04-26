# Skill Quality Scorecard

Use this scorecard when reviewing an output produced with one of the skills in this repository. It
is a maintainer evaluation aid, not a scientific benchmark and not proof of model correctness.

## Scoring

- `0 = missing`: the behavior is absent or contradicts the skill.
- `1 = weak`: the behavior appears, but is generic, incomplete, or weakly supported.
- `2 = acceptable`: the behavior is present, useful, and mostly aligned with the skill.
- `3 = strong`: the behavior is specific, evidence-based, complete, and ready for handoff.

## Criteria

| Criterion | What To Look For |
| --- | --- |
| Context awareness | Uses the supplied issue, repo, acceptance criteria, environment, and constraints instead of giving generic advice. |
| Evidence discipline | Separates facts, assumptions, unknowns, and missing evidence; cites inspected context when making claims. |
| Correct handoff to related skills | Routes unclear product intent, missing root cause, review needs, manual testing, or automation decisions to the right skill. |
| Output contract completeness | Includes the required sections and fields for the skill, marking unavailable items honestly. |
| Specificity/actionability | Produces concrete next steps, risks, fixes, test ideas, or questions that a maintainer can act on. |
| Hallucination avoidance | Does not invent ticket details, logs, test runs, root cause, stakeholder approval, company rules, or private systems. |
| Test/validation realism | Recommends validation that is feasible for the context and does not claim checks were run unless they were run. |
| Risk awareness | Identifies user, product, security, operational, regression, compatibility, or release risks relevant to the task. |
| Correct stopping behavior | Stops or asks for context when required inputs are missing, instead of producing confident but unsupported output. |
| Portability/public-safety | Avoids private data, hardcoded company standards, local paths, real customer examples, or unsafe production actions. |

## Suggested Review Method

1. Run or read the relevant eval scenario from [`evals/`](../evals/).
2. Ask the agent to use the target skill with the supplied input context.
3. Score each criterion from `0` to `3`.
4. Review any `0` or `1` as a possible skill wording problem, eval ambiguity, or model limitation.
5. Record only actionable findings. Do not overfit the skill to one model's phrasing.

## Interpreting Scores

- `24-30`: strong behavior for a manual eval; look for small wording or handoff improvements.
- `18-23`: usable but may need sharper guardrails, output fields, or stopping conditions.
- `10-17`: weak; review the skill workflow and output contract before release.
- `<10`: not release-ready for this scenario.

A low score does not automatically mean the skill is broken. It may mean the prompt was missing
required inputs, the model lacked tools, or the eval scenario needs clearer expected behavior.
