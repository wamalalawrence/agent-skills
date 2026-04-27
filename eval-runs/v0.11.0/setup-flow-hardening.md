# Setup Flow Hardening — v0.11.0 Eval Run

- Release: `v0.11.0`
- Category: maintainer-authored (illustrative).
- Scope: engineering hardening of `setup.init`, `.env.example`, and
  `.agent-skills.example.yml`. No `SKILL.md` content changed.

## Scenario

A new public-good user clones `agent-skills` and runs `./setup.init` for the
first time. They have a Jira host and want Confluence too. They have made the
common mistake of pasting an API token when asked for project keys, and have a
legacy `.env` from a previous release with duplicate top-level keys.

## Inputs

- Workspace root: `~/work` containing `agent-skills/` and three sibling repos.
- Jira host: `https://acme.atlassian.net`.
- Jira login: `person@acme.example.com`.
- A pasted ticket URL: `https://acme.atlassian.net/browse/PLAT-123`.
- A legacy `.env` containing `ORG_NAME`, `JIRA_HOST`, `JIRA_API_TOKEN`,
  `PROJECTS_JSON` defined OUTSIDE any marker block.

## Expected behaviour (contract)

- `./setup.init` infers `ORG_NAME` as `Acme` from the Jira host.
- `./setup.init` infers `ORG_DOMAIN` as `acme.example.com` from the login.
- `./setup.init` infers `CONFLUENCE_HOST` as `https://acme.atlassian.net/wiki`.
- The `Jira project keys` prompt extracts `PLAT` from the pasted ticket URL.
- If the user pastes a long random API-token shape, the prompt rejects it with
  a clear "that looks like an API token" warning before storing.
- The legacy `.env` keys outside the marker block are removed and reported in
  the run output ("Removed N duplicate setup-managed key(s)").
- Generated `.env` and `.jira-config.yml` are `chmod 600`.
- The Jira and Confluence tokens are never echoed in any log output.
- `./setup.init --verify` reports "no duplicate managed keys" and "Verification
  passed".

## Actual run (smoke-tested locally during release)

- Migration smoke test under `tmp/work` produced output:
  `Removed 4 duplicate setup-managed key(s) outside the marker block.`
- Verifier reports `ok    no duplicate managed keys` and exits 0 on rerun.
- CI step `Verify setup.init non-interactively` extended to assert that the
  managed-key count outside the marker block is zero after both first run and
  rerun, and that an explicit `--with-confluence` non-interactive flow writes
  empty Confluence values without raising errors.

## Score (5-point)

- Correctness of the duplicate-key fix: 5/5.
- Auto-population correctness: 4/5.
- Prompt clarity and examples: 5/5.
- Secret hygiene: 5/5.
- Documentation alignment (CHANGELOG, configuration, installation,
  execution-modes): 5/5.

## Follow-ups recorded for future releases

- Add an `expect`-style harness to exercise interactive prompts in CI.
- Support multi-ticket project-key inference (e.g. paste `ABC-1, PLAT-2`).
- Add a `--rotate-secrets` flow that invalidates and reprompts only secret
  fields without rewriting non-secret managed keys.
