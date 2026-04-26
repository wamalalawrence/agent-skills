# Severity And Confidence

Use these shared definitions whenever a skill reports findings, defects, review results, or
investigation confidence. Severity describes impact if the issue is real. Confidence describes how
strong the evidence is.

## Severity

- `blocker`: likely wrong behavior, broken build, data loss, security/privacy exposure, unsafe
  migration, missing core acceptance criteria, or production-incident risk. Blocking unless explicitly
  waived.
- `major`: meaningful correctness, maintainability, compatibility, test, operational, or
  user-impact risk that should normally be addressed before merge, release, or handoff.
- `minor`: real issue or improvement with limited blast radius. Worth fixing when nearby, but not
  usually blocking by itself.
- `nit`: small clarity, naming, wording, or cleanup note. Do not use for formatter/linter noise
  unless it affects readability or maintainability in a way automated tools will not catch.

Severity is not effort. A one-line auth bug can be a blocker; a large refactor preference can be a
nit or not worth reporting.

## Confidence

- `high`: direct evidence supports the claim, such as a failing test, observed reproduction, code
  path, log line, trace, documented requirement, or CI result.
- `medium`: evidence points in the same direction, but at least one material assumption or missing
  check remains.
- `low`: plausible but weakly supported. Use to surface uncertainty, not to justify blocking action
  unless the possible impact is severe and needs investigation.

## Root-Cause Status

Used by `issue-investigator` and consumed by downstream skills.

- `unknown`: no candidate cause is supported strongly enough to recommend a fix. Continue gathering
  evidence or ask for missing context.
- `suspected`: a candidate cause fits the evidence and has a falsifiable path, but has not been
  fully confirmed. Suitable for planning limited experiments, observability, or a cautious fix only
  when paired with a reproducible recipe.
- `confirmed`: the cause is supported by reproduction, code/log/data evidence, or a discriminating
  experiment that rules out credible alternatives.
- `disproved`: a candidate cause was tested and contradicted by evidence. Keep the disproving
  evidence in the investigation notes so later work does not repeat the same path.
