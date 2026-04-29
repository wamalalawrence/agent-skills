# v0.18.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.18.0`. It scores the new Jira /
Confluence auth-discovery contract that prevents agents from reporting "I can't access Jira"
when `.env` and `.jira-config.yml` are present in the workspace.

Category: maintainer-authored (illustrative).

## Scope of this release

- New `docs/auth-discovery.md` — explicit discovery order, placeholder resolution, CLI-
  independent guidance, and a troubleshooting table for the most common "no auth" failures.
- New `scripts/auth-preflight.py` — dependency-free, redacts every secret value, exit codes
  `0` / `1` / `2` for usable / incomplete / setup-error, JSON output for skill consumption.
- New `evals/auth-discovery-jira-confluence.md` — eval scenario covering the exact failure
  mode (placeholders unresolved, agent reports "no auth" prematurely).
- Mandatory auth-discovery step added to `software-engineer`, `issue-investigator`, and
  `code-reviewer` Required Environment sections.
- `check_jira_placeholder_consistency` validation prevents `.jira-config.example.yml` from
  drifting away from `.env.example` (unreferenced `${VAR}` would silently sit unresolved).
- `.env.example`, `.jira-config.example.yml`, `.agent-skills.example.yml` reword the
  cross-file relationship so a reader (human or agent) understands where values live and
  how placeholders are resolved.
- No new skills, no skill renames, no new required env vars.

## Scoring summary

- Discovery-order clarity: 5/5. The order is identical across the doc, the three skill
  changes, and the eval — `.agent-skills.yml` → `.jira-config.yml` → `.env` / `.env.local`
  → process env → preflight → ask. The deliberate "discovery walk vs. resolution
  precedence" inversion is explained.
- Secret hygiene: 5/5. The preflight script never prints secret values; the human-readable
  output redacts to `set (hidden)`, the JSON output reports `value_present: bool` only.
  `--show-prefix` only affects non-secret values.
- Placeholder semantics: 5/5. Unresolved `${VAR}` placeholders are classified as
  **incomplete configuration**, not missing auth. The skills explicitly forbid the
  premature "no auth" failure. The validator catches placeholders that drift away from
  `.env.example`.
- CLI independence: 4/5. Skills no longer assume the `jira` CLI is present or that it
  expands placeholders. The preflight works without any CLI installed. The remaining gap:
  the skills still reference `${JIRA_CONFIG_FILE}` for advanced flows, which is fine for
  CLI users but worth re-reading on a future pass.
- Surgical-edit discipline: 5/5. One new doc, one new script, one new eval, one new
  validator check, one CHANGELOG entry, version bump. No new skills, no renames, no
  required-env-var additions.
- Public-good portability: 5/5. Every example uses `example.atlassian.net`, `ABC,PROJ`,
  and redacted placeholders. No private hosts, no real ticket prefixes, no real emails.

## Reviewer self-rebuttal

The most credible scenario in which this release is wrong:

- An in-repo / cloud-agent run cannot execute `python3 scripts/auth-preflight.py` because
  the agent's host doesn't allow shell-out, so the discovery walk degrades to "read the
  config files in order and rely on the agent's own judgment". The doc handles this — it
  presents the preflight as one of several discovery steps, not the only one — but a
  paranoid reviewer might want a pure-prose checklist the agent can run mentally without
  the script. v0.19.0 may add an explicit "preflight-as-instructions" appendix.

- The script's YAML parser is hand-written and only understands `installation`, `server`,
  `login`, and `auth_type` keys. A more elaborate `.jira-config.yml` (epic/board/issue
  blocks, custom fields) is parsed but ignored. That is intentional — the preflight only
  cares about auth-relevant fields — but it should be called out in the doc if a future
  user expects "validate my entire `.jira-config.yml`". For now, the README of the script
  states the scope.

## Pass / fail summary

The release passes maintainer review. Validation runs were green; the auth preflight runs
clean against the example fixture set. No regressions to existing skills or eval runs.
