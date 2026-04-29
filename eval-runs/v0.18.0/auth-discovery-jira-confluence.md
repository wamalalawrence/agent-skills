# v0.18.0 Eval Run: Auth Discovery (Jira / Confluence)

**Eval scenario:** `evals/auth-discovery-jira-confluence.md`
**Skills under test:** `issue-investigator` (primary), `software-engineer`, `code-reviewer`.
**Run date:** maintainer dry-run for the v0.18.0 release.
**Workspace fixture:** `.env` and `.jira-config.yml` co-located, placeholders unresolved
until `.env` is sourced.

## Run notes

The eval was executed as a paper walkthrough plus a real run of `scripts/auth-preflight.py`
against three synthetic fixtures: (1) usable Jira + usable Confluence, (2) Jira config
incomplete (token missing) and Confluence host blank, (3) `.jira-config.yml` placeholders
unresolved with no `.env` present.

The skills were exercised by reading their updated Required Environment sections against
each fixture and asking: "what would the agent do here?". Where the answer would be a
silent fall-back to 'no Jira access', the SKILL.md was reworded so the discovery walk is
mandatory.

## Findings

- The preflight resolves the placeholders against `.env` and reports usable when the
  fixture provides matching values. It exits `0`. No secret value appears in stdout.
- The preflight reports `unresolved placeholder ${JIRA_HOST}` when `.jira-config.yml`
  references it but no `.env` provides it — distinct from "missing field" — so the agent
  can tell the user which non-secret to fix.
- The preflight detects an API-token-shaped value pasted into `JIRA_PROJECT_KEYS` and
  redacts it to `<first-2>***<last-2>` while recommending rotation through normal
  channels.
- Confluence-host blank is reported as **skipped**, not blocked. The script exits `0`
  when only Jira is required.
- The skill changes prevent the failure mode the eval targets: an agent reading
  `.jira-config.yml` without sourcing `.env` would have previously reported "no Jira
  access". With v0.18.0, the discovery walk is the SKILL-required first step.

## Pass / fail

- [x] Discovery walk is performed before any "auth unavailable" claim.
- [x] When `.env` provides values referenced by `.jira-config.yml`, the agent treats Jira
  as available without asking the user for credentials.
- [x] No secret value appears in chat, the evidence pack, or any cached artifact.
- [x] Confluence is reported as "skipped" rather than "blocked" when `CONFLUENCE_HOST` is
  blank.
- [x] Unresolved `${VAR}` placeholders are reported by name, distinct from missing
  secrets.
- [x] When auth is genuinely incomplete, the agent's ask names the specific
  missing/unresolved fields and points to the configured secret-injection path, not chat.

Result: **pass**. Maintainer-authored, illustrative.
