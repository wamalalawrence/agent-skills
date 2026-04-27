# v0.11.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.11.0`. It scores the
non-skill engineering improvements that ship in this release: the setup-flow
hardening, duplicate-key fix, configuration auto-population, and Confluence
support. No `SKILL.md` content changed in this release.

Category: maintainer-authored (illustrative).

## Scope of this release

- Restructured `.env.example` so every setup-managed key lives inside one
  `# >>> agent-skills setup.init` ... `# <<< agent-skills setup.init` marker
  block. The block is the single source of truth.
- Replaced the prompt flow in `setup.init` with help-text-bearing prompts that
  state REQUIRED-WHEN, give an EXAMPLE, and indicate optionality.
- Added Confluence configuration (host, login, token, space keys) with
  inference from the Jira host where possible.
- Added inference helpers for `ORG_NAME` (from Jira host or GitHub org),
  `ORG_DOMAIN` (from login email, Jira host, or GitHub org), Jira project keys
  (from a pasted ticket key like `ABC-123` or ticket URL), and the Confluence
  host (from the Jira host).
- Added input validators (URL shape, email shape, project-key shape, JSON
  parse) and a strict rejection for API-token-shaped values when project keys
  are requested.
- Added `--with-confluence` / `--no-confluence` flags and Confluence verify
  output.
- Added a stripper that removes legacy duplicate setup-managed keys from
  `.env` files outside the marker block (one-time migration on rerun).
- Added a repo-validator check that fails the build when any setup-managed
  key appears outside the marker block in `.env.example`.
- Added 0600 permissions on generated `.env` and `.jira-config.yml`.
- Documented the new in-repo Confluence block in `.agent-skills.example.yml`.

## Scoring summary

Each item below scores the user-visible improvement on the 5-point scale used
by previous eval runs (1=poor, 5=excellent).

- Duplicate-key root cause fix: 5/5. Markers + outside-block stripper + CI
  validator make duplicates structurally impossible.
- Auto-population of `ORG_NAME`/`ORG_DOMAIN`/`GITHUB_ORG`/Jira project key:
  4/5. Cleanly chained inferences. Jira project key inference from pasted
  ticket URL/key works in interactive mode; non-interactive mode still relies
  on user input.
- Prompt clarity (REQUIRED-WHEN, EXAMPLE, optional/blank guidance): 5/5.
- Confluence setup: 4/5. Optional, inferred from Jira host, secret never
  echoed, written only to gitignored `.env`. Server / Data Center hosts may
  need manual override (covered by inference fallback).
- Validation (URL, email, project key, JSON, duplicate keys): 4/5. Reject
  obvious API tokens disguised as project keys. JSON validation already
  existed.
- Public-safety guarantees: 5/5. Secrets are never echoed; generated files
  are 0600; `.env` and `.jira-config.yml` remain gitignored; placeholders
  use `acme.example.com` only.
- In-repo mode parity: 4/5. `.agent-skills.example.yml` now documents
  Confluence and ORG_DOMAIN; secrets remain host-injected.

## Common gaps (carry forward)

- No automated browser-based test of an interactive `setup.init` run; the
  CI test exercises only `--yes` flows. A future release should add an
  `expect`-style harness.
- The Jira project-key inferer accepts a single ticket as a single project;
  pasting multiple tickets is not supported yet.
- Self-hosted Confluence inference assumes a `jira.<domain>` to
  `confluence.<domain>` rewrite. Custom hostnames still need manual entry.

## Changes Made For v0.11.0

- See `CHANGELOG.md` 0.11.0 section.
- `VERSION` bumped to `0.11.0`.
- All `SKILL.md` `metadata.version` values bumped to `0.11.0`.
- `scripts/validate-repo.py` extended with `check_env_example_marker_block`.
- `.github/workflows/ci.yml` extended to assert no duplicate managed keys
  and to exercise `--with-confluence` non-interactively.

## Not Changed (deliberate)

- No skill wording changes.
- No new top-level skills.
- No new nested skills.
- No changes to evaluation scoring rubric.
