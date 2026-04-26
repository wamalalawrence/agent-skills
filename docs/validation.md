# Validation

This repository uses lightweight validation to catch structural regressions before skill changes are
released. The checks are intentionally simple: standard-library Python, no required secrets, and no
model calls.

## How To Run

From the repository root:

```bash
python3 scripts/validate-repo.py
```

The older command still works as a compatibility wrapper:

```bash
python3 scripts/validate_skills.py
```

GitHub Actions runs the same repository validator on pushes and pull requests to `main`.

## What It Checks

- Required repository files, docs, config examples, skill files, and evaluation scenarios exist.
- Important Markdown files are not collapsed into one or two giant lines.
- Markdown headings exist and fenced code blocks are balanced.
- Markdown source remains readable: overlong lines, mid-line headings, collapsed table rows, and
  mid-line code fences are rejected.
- YAML and Python source receive similar line-readability checks where reasonable.
- Basic relative Markdown links resolve to files or folders in the repository.
- Every `SKILL.md` has the required sections:
  `Purpose`, `When To Use`, `Related And Reused Skills`, `Required Inputs`, `Required Workflow`,
  `Expected Output Contract`, `Quality Standards`, `Guardrails`, and `Example Prompts`.
- Every `SKILL.md` has parseable frontmatter with `name`, `description`, `license`,
  `compatibility`, `metadata.author`, `metadata.version`, and `metadata.homepage`.
- Skill metadata versions match `VERSION`, and `CHANGELOG.md` contains an `Unreleased` section.
- Required links between related skills are present.
- Obvious public-safety problems are flagged, including likely secrets, private local paths,
  suspicious private hostnames, possible real emails, and hardcoded ticket keys.
- Generated, cache, and local-private files are not tracked by git.

## What It Does Not Check

- It does not prove that an AI model will follow the skill perfectly.
- It does not run the eval scenarios automatically or score model output.
- It does not validate private systems such as Jira, CI, issue trackers, credentials, or customer
  environments.
- It does not prove factual correctness of examples, investigation results, code reviews, or test
  plans.
- It does not replace maintainer review of wording, scope, portability, or usability.

## Warnings Vs Failures

Failures exit with a non-zero status and should block a release. Examples include missing required
files, broken relative links, malformed skill frontmatter, missing required skill sections, version
mismatches, unbalanced code fences, unreadable long source lines, tracked cache files, likely
secrets, or private absolute paths.

Warnings exit successfully but should still be inspected. Examples include suspicious hostnames,
possible real emails, hardcoded ticket keys, README/version drift, or local generated/cache files
that exist in the working tree without an ignore rule.

## Evaluation Scenarios

The files in [`evals/`](../evals/) are manual scenario checks for skill behavior. They are designed
to help maintainers ask: given this input context, would the skill produce evidence-based, specific,
contract-complete output without inventing missing facts?

Use the [skill quality scorecard](skill-quality-scorecard.md) to judge outputs consistently. Treat
the scorecard as a maintainer aid, not a scientific benchmark.

## Why This Is Limited

The validator can catch broken structure, missing links, version drift, and obvious public-safety
mistakes. It cannot guarantee model correctness because model behavior depends on the host agent,
available tools, retrieved context, user prompt, runtime state, and the model itself. Passing
validation means the skill package is coherent enough to review and try; it does not mean every
future AI output will be correct.
