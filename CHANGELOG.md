# Changelog

All notable project changes should be recorded here.

## Unreleased

### Added

- **`docs/quickstart.md`** — short first-time user path covering what the repository is, when to use
  it, how to invoke one skill manually, both execution modes, and starter prompts for the four
  top-level skills.
- **`docs/known-limitations.md`** — public limitations for non-deterministic agent behavior,
  nested-skill support, external access, company-specific standards, human review, cache behavior,
  and no-warranty/no-SLA expectations.
- **`docs/versioning.md`** — pre-1.0 and post-1.0 versioning policy. Before `v1.0.0`, minor releases
  may change structure or output contracts; patch releases should focus on docs, formatting,
  compatibility, examples, validation fixes, and non-breaking clarifications.

### Changed

- Reformatted Markdown and YAML files so raw files and diffs are readable: headings, lists, tables,
  code fences, frontmatter, configuration templates, skill files, support docs, and reference docs.
- Replaced the broken README skills table and collaboration diagram with a GitHub-renderable table
  that clearly distinguishes the four top-level skills from the two nested support skills.
- Added README links to the quickstart, known limitations, and versioning policy.
- Polished `SUPPORT.md` and `GOVERNANCE.md` to keep solo-maintainer boundaries while using a more
  neutral public tone.
- Updated the skill validator fallback parser so CI can validate multi-line frontmatter even when
  PyYAML is unavailable.
- Bumped release-prep version references from `0.6.0` to `0.6.1`.

## 0.6.0 - In-Repo Execution Mode (Online / Cloud Agent Support)

Until now the project assumed every user runs an AI assistant locally with `agent-skills` cloned
alongside their other repos. Cloud / online agents (GitHub Copilot coding agent on github.com,
Cursor cloud, Devin, Codex, Codespaces, Gitpod, Claude.ai web with the repo attached) operate inside
a single target repository — no sibling `agent-skills` checkout, no `setup.init` shell access, no
`${WORKSPACE_ROOT}/.env`. v0.6.0 makes this a first-class second mode instead of an undocumented
edge case.

### Added

- **`docs/execution-modes.md`** — single source of truth for the two modes (`local-workspace` and
  `in-repo`), how skills detect which one applies, and the variable-resolution order each uses.
- **`.agent-skills.example.yml`** — committed-to-repo configuration template for `in-repo` mode.
  Holds the single `project:` block and the org/github/jira-host metadata previously read from
  `.env`. Contains **no secrets**; credentials still come from environment variables injected by the
  host platform.
- README install section now documents both paths explicitly: "Local workspace" (the existing
  `setup.init` flow) and "In-repo" (the new path for online agents).
- `docs/installation.md` opens with an "in-repo install" section for cloud-agent users.
- `docs/configuration.md` documents the `.agent-skills.yml` schema, the precedence order (env → file
  → repo-file inference → stop), and the cache-path resolution.
- `docs/assistants.md` adds a section covering GitHub Copilot coding agent, Cursor cloud,
  Devin/Codex, Codespaces/Gitpod, and Claude.ai web.

### Changed

- **All 6 SKILL.md preflight blocks** updated to detect mode (`AGENT_SKILLS_MODE` →
  `${WORKSPACE_ROOT}/.env` → `.agent-skills.yml` → stop), then resolve required values in
  `local-workspace` or `in-repo` mode without assuming `${WORKSPACE_ROOT}/.env` exists. The "Missing
  required setup" error message now points at whichever config file matches the detected mode.
- **All 6 SKILL.md `compatibility:` frontmatter** rewritten to declare both modes and link to
  `docs/execution-modes.md`.
- **All cache-path references** in skills and reference docs changed from the hardcoded
  `${WORKSPACE_ROOT}/.cache/agent-skills/...` to
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills/...}` — works in both
  modes; can be overridden by setting `AGENT_SKILLS_CACHE_DIR`.
- README status banner bumped to `0.6.0`. All SKILL.md `metadata.version` bumped to `0.6.0`.

### Not changed

- `setup.init` behaviour and the `local-workspace` install path are unchanged. v0.5.0 setups
  continue to work as-is.

## 0.5.0 - Evidence Pack, Definition of Done, Honest Contribution Framing

The infrastructure half of the v0.4.0 plan (G1, G2, G9, G10) plus an honesty pass on the
contribution/governance/support docs.

### Added

- **`skills/software-engineer/references/evidence-pack.md`** — the schema for `evidence-pack.yml`
  and `repro-recipe.yml`. Cached at `${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/`. Defines
  what each skill reads and writes so `issue-investigator`, `software-engineer`, `code-reviewer`,
  `manual-tester`, `test-automation-engineer`, and `product-owner` stop re-deriving context on every
  hop.
- **`skills/software-engineer/references/definition-of-done.md`** — the schema for
  `definition-of-done.json`, the Phase 5 gate artifact the reviewer must verify before declaring
  `PASS`. Includes bug-fix-specific fields (regression-test commit, fails-on-parent, passes-on-head,
  observability_added) and operational hygiene flags (`no_no_verify`,
  `branch_starts_with_ticket_key`, `no_unrelated_files`).
- **`software-engineer` Phase 5.3 — Definition-of-Done artifact step.** The engineer now writes the
  DoD JSON before opening the PR; `--no-verify` is explicitly forbidden without a written waiver.
- **`software-engineer` Phase 1.4 + 1.5** persist the 5-line plan and reference the repro recipe
  path in the evidence pack.
- **`code-reviewer` hard handoff contract** now reads from the on-disk evidence pack and DoD
  artifact and surfaces specific missing fields as `major` findings; any `false` flag in the DoD
  without a waiver is itself a `blocker`.
- **`issue-investigator`** now persists the full investigation result and repro recipe to the cache
  so downstream skills can consume them directly.
- **`test-automation-engineer`** seeds regression tests directly from `repro-recipe.yml`
  (`prerequisites`, `steps`, `expected_observation`, `post_fix_observation`).
- **`manual-tester`** writes its repro recipe to the same shared file when the defect is
  reproducible.
- **`product-owner`** writes refined `acceptance_criteria` back to the shared evidence pack.

### Changed

- **README, CONTRIBUTING.md, GOVERNANCE.md, SUPPORT.md rewritten to drop the welcoming-but-ignored
  contradiction.** The project is solo-maintained and exists primarily for the maintainer's own
  engineering work, shared as a public good. Issues and PRs are not actively solicited; forking is
  the recommended path for divergent needs. The new files set realistic expectations up front
  instead of implying a contributor pipeline that does not exist.
- README status banner bumped to `0.5.0`.
- All six `SKILL.md` files: `metadata.version` bumped to `0.5.0`.

## 0.4.0 - Accuracy & Cross-Skill Collaboration

Anchored to the engineering fundamentals the skills are meant to enforce: full context awareness, no
guessing, real root-cause investigation, safe-environment reproduction, and engineer↔reviewer
pair-programming.

### Added

- **README cross-skill graph.** The skills table now shows _Reuses / collaborates with_ instead of
  just folder nesting, plus an ASCII collaboration diagram. Makes it explicit that
  `test-automation-engineer`, `manual-tester`, and `product-owner` all reuse the other roles — that
  information previously lived only inside each `SKILL.md`.
- **`software-engineer` Phase 1.5 — Reproduce-before-fix gate.** Bug fixes must now write a failing
  regression test FIRST, commit it as the first commit on the branch (verifiable by checking out the
  parent), and only then implement the fix. Refactors / formatting / docs / new features are
  explicitly exempt.
- **`software-engineer` 5-line plan structure** (Problem · Hypothesis · Smallest change · Risk ·
  Validation) so the reviewer can later check the diff against the stated intent.
- **`software-engineer` self-review item — fix-adds-observability.** If the defect was hard to
  investigate because evidence was missing, the fix must add the missing log/metric/correlation id.
- **`issue-investigator` safe reproduction protocol.** Operational ladder (local stack → ephemeral
  env → replayed input → read-only inspection of affected env), with a deterministic recipe captured
  for handoff to engineer/test-automation-engineer.
- **`issue-investigator` three-hypothesis discipline.** Top-3 candidate causes, falsifiable "what
  would change my mind" line per hypothesis, single cheapest discriminating experiment. Replaces the
  vague "avoid stopping at the first plausible explanation" guidance with a concrete technique.
- **`issue-investigator` regression triage** (`git log -L`, `git blame`, `git bisect`,
  deploy/feature-flag diff) before forming hypotheses for any reported regression.
- **`issue-investigator` confidence gate** mapping each recommended next-action (code fix / rollback
  / config change / monitoring / clarification) to the minimum root-cause confidence required to
  recommend it.
- **`code-reviewer` hard handoff contract** listing the evidence pack the engineer must supply
  (project entry, issue brief, root-cause confidence, failing-test commit for bug fixes, 5-line
  plan, risk areas). Missing handoff is a `major` finding.
- **`code-reviewer` `test-quality` review profile** for `manual` mode when reviewing test code
  (selector stability, deterministic data, condition-based waits, assertion meaningfulness,
  isolation).
- **`code-reviewer` iteration convergence rule (`CODE_REVIEWER_MAX_ROUNDS`, default `3`).**
  Blocker+major finding count must strictly decrease between rounds; non-converging loops escalate
  to the user instead of grinding indefinitely or silently downgrading blockers.
- **`code-reviewer` devil's-advocate self-rebuttal** before any `PASS` verdict, attacking your own
  conclusion against silent data loss, lost-update / race conditions, auth bypass, secret/PII
  leakage, broken migration, breaking API contract, and regression risk.
- **`test-automation-engineer` invokes `code-reviewer`** in `test-quality` mode on its own test
  code, plus a flake-budget rule (≥20 repeat executions in CI before merge), explicit anti-pattern
  list (`Thread.sleep`, `cy.wait(N)`, `time.sleep`, hard-coded dates, ordering-dependent fixtures,
  shared mutable test data, blind retries), and links to the originating `issue-investigator` recipe
  for regression-derived tests.
- **`manual-tester` safe reproduction protocol** mirroring `issue-investigator`, plus a
  defect-template _investigator handoff_ field, mandatory commit-SHA in defect reports, replayable
  artifact preference (HAR / Playwright trace / Cypress recording), and time-boxed exploratory
  charters.
- **`product-owner` routes bug-flavored input through `issue-investigator` first.** Support tickets,
  incidents, regression complaints, etc. are not turned into acceptance criteria until investigation
  results are in hand — closes a guessing path that previously let the PO invent "actual behavior".
- **`product-owner` Definition-of-Ready gate** before producing the Jira-ready output (goal stated,
  investigator result attached for bug-flavored input, observable/testable ACs with at least one
  negative criterion, scope explicit, feasibility note attached for
  API/migration/security/shared-library work, open questions listed).
- **`product-owner` requires at least one negative AC** (`Given X, the system MUST NOT Y`) per work
  item.
- **`product-owner` feasibility-note artifact** (effort tier, key risks, breaking-change y/n) from
  `software-engineer` before locking acceptance criteria.

### Changed

- README status banner bumped to `0.4.0`.
- All six `SKILL.md` files: `metadata.version` bumped to `0.4.0`.

## 0.3.0 - Spec Alignment And Slim README

### Added

- `compatibility:` and `metadata:` (author, version, homepage) frontmatter on every `SKILL.md`,
  conforming to the [Agent Skills specification](https://agentskills.io/specification).
- `scripts/validate_skills.py` — a self-contained validator that checks every `SKILL.md` against the
  spec (`name` 1-64 chars + matches parent dir, `description` 1-1024 chars, `compatibility` <= 500
  chars, `metadata` shape, `license` non-empty when present).
- GitHub Actions CI workflow at `.github/workflows/ci.yml` that runs the skill validator, exercises
  `setup.init --yes` and `--verify` end-to-end against a temp git workspace (including idempotency
  and `$HOME`-refusal assertions), and runs a markdown link check.
- `npx skills add wamalalawrence/agent-skills` documented as an alternative install path via the
  [skills.sh](https://skills.sh) ecosystem.
- `docs/` directory: `installation.md`, `configuration.md`, `assistants.md`, `prompts.md` —
  long-form material moved out of the README.

### Changed

- README rewritten to be short and scannable in the GitHub preview (~60 lines vs ~280 before):
  tagline, why-skills, install, skills table, links into `docs/`, principles, contributing, license.
  Inspired by `google/skills` README pacing.
- Skill internal links updated to point at `docs/` for installation/configuration/assistant
  compatibility/starter prompts.

## 0.2.0 - Onboarding And Positioning

### Added

- `setup.init`: bash automation for first-run workspace setup. Asks a short set of questions, then
  creates or refreshes `.env`, `.jira-config.yml` (optional), the `.skills` symlink, and an
  idempotent agent-skills block in the workspace `.gitignore`.
- `setup.init --verify`: re-checks an existing setup without writing — required env vars,
  `PROJECTS_JSON` shape, every project path resolves, `.skills` target valid, Jira credentials
  consistent.
- "Why Skills" section in the README explaining how a skill turns a generalist LLM into a specialist
  (general practitioner vs. dentist analogy).
- "Try A First Prompt" section in the README with one starter prompt per skill.
- Honest "Using With Your AI Assistant" compatibility table covering Claude Code,
  Cursor/Windsurf/Continue, GitHub Copilot Chat, and generic chat clients.

### Changed

- README Quick Start now leads with `./setup.init` and an explicit recommended workspace layout,
  with manual `cp` setup retained as a fallback.
- `.env.example` headers point at `setup.init` and ship safer bootstrap defaults.
- Nested `code-reviewer` README clarifies that `CODE_REVIEWER_MODEL` is optional, not required.

### Hardened

- `setup.init` refuses unsafe workspace roots (`$HOME`, `/`, and common system directories) so a
  fresh clone in the wrong place cannot pollute your shell environment. Explicit `--workspace-root`
  requires interactive confirmation to override.
- JSON validation prefers `python3` (universally present), falls back to `ruby`, and only skips with
  a warning when neither is installed.
- `GITHUB_ORG` is detected from sibling repository `remote.origin.url` first, then falls back to
  `gh api user --jq .login`, then leaves the field blank.
- Build and format commands are inferred per package manager: `pnpm`/`yarn`/`bun`/`npm` lockfiles
  plus `package.json` script presence; Poetry-aware Python; gradle fallback when no wrapper is
  present.
- The generated `.env` block carries an explicit warning that contents inside the markers are
  overwritten on rerun and that manual edits belong outside the markers.
- The generated workspace `.gitignore` block covers `.env`, `.env.local`, `.env.*.local`,
  `.jira-config.yml`, `.skills`, and `.cache/` so workspaces that are themselves git repos do not
  show those files as uncommitted changes (and `.env` does not risk leaking secrets). Idempotent on
  rerun.

### Documentation

- CONTRIBUTING.md documents the `setup.init` validation expectation for contributors.

## 0.1.0 - Initial Public Baseline

- Added the initial `software-engineer` role skill.
- Added nested review and Jira-driven issue resolution skills under `software-engineer`.
- Added reference checklists for code review, security, SonarQube-style quality gates, and
  architecture patterns.
- Added environment and Jira configuration templates.
