# Changelog

All notable project changes should be recorded here.

## Unreleased

- No unreleased changes.

## 0.19.0 - Skill-Source Resolution And Self-Update

### Added

- New [`docs/skill-source-resolution.md`](docs/skill-source-resolution.md) — the canonical
  agent-facing reference for which skill directory to load when more than one is present on
  disk. Defines a six-step resolution order (`.agent-skills.yml` `skills.canonical_dir` →
  repo-modification context → `.agent-skills/skills/` → `.skills/` → `agent-skills/skills/` →
  ask the user when ambiguous), the duplicate-handling rules (no merging, no "load all", warn
  on version drift), and the mode-specific defaults that match what `setup.init` ships.
- New [`docs/updates.md`](docs/updates.md) — how a user who has already cloned the repo
  notices a new release and applies it. Documents three update channels (`./setup.init
  --check-updates`, `./setup.init --update`, manual `git pull`), the in-repo / vendored update
  flow, the rollback path, and how the agent surfaces drift between the loaded skill version
  and the workspace lock file.
- New [`scripts/check-updates.py`](scripts/check-updates.py) — dependency-free Python tool
  that compares the local `VERSION` (or the highest `metadata.version` under a vendored
  `skills/` directory) against the latest release tag on `origin`. Supports `--vendored`,
  `--json`, `--use-api`, `--token` (read from `--token` or `GITHUB_TOKEN`, never echoed). Exit
  codes: `0` up-to-date / ahead, `10` update available, `2` setup error.
- New `setup.init --check-updates` subcommand — same comparison as the standalone script,
  but workspace-independent. Same exit codes.
- New `setup.init --update` subcommand — fetches tags from `origin`, refuses to act on a
  dirty working tree, checks out the latest release tag (or `--branch NAME`), then re-runs
  the setup flow non-interactively to refresh `.skills` and the new `.agent-skills.lock`
  metadata file. Never pushes, never auto-updates without the explicit flag.
- New advisory `<workspace>/.agent-skills.lock` file written by every `setup.init` run.
  JSON, gitignored, schema `agent-skills.lock/v1`. Records `version`, `git_sha`,
  `canonical_dir`, `source_repo_dir`, `installed_at`, `installed_by`. Lets agents pin to a
  known version and detect drift without inspecting the source repo.
- New `skills:` block in [`.agent-skills.example.yml`](.agent-skills.example.yml) covering
  `canonical_dir`, `duplicate_policy`, `source_repo_dir`, `allow_source_repo_fallback`, and
  `warn_on_version_drift`. All keys are optional; defaults match the resolution order.
- New [`evals/skill-source-resolution-ambiguity.md`](evals/skill-source-resolution-ambiguity.md)
  eval scenario covering the exact failure mode this release targets: a workspace with both
  `.skills/` and a vendored `.agent-skills/skills/` copy at different versions, agent must
  walk the resolution order rather than merging or arbitrarily picking.
- `eval-runs/v0.19.0/` capturing the skill-source-resolution scenario and the release summary.

### Changed

- `setup.init` now writes `.agent-skills.lock` at the end of every run, surfaces a warning
  when more than one **distinct** skill source exists in the workspace without a configured
  `skills.canonical_dir`, and reports lock-file status (matched / drifted / missing) in
  `--verify`. The ambiguity check resolves symlinks before comparing, so the expected
  `.skills -> agent-skills/skills` shape is **not** flagged.
- `setup.init --help` documents `--check-updates`, `--update`, and `--branch`.
- The setup-managed `.gitignore` block now ignores `.agent-skills.lock`.
- `scripts/validate-repo.py` `REQUIRED_FILES` extended with the new docs, eval, eval-runs,
  and `scripts/check-updates.py`. New `check_agent_skills_yaml_skills_block` validation
  ensures `.agent-skills.example.yml` keeps the documented `skills:` block keys.
- `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/installation.md`,
  `docs/configuration.md`, `docs/assistants.md`, `docs/execution-modes.md`, and
  `docs/known-limitations.md` link the two new docs.
- `VERSION` and every `SKILL.md` `metadata.version` bumped to `0.19.0`.

### Why

A user who clones `agent-skills` next to other repos and runs `./setup.init` ends up with
at least two paths that contain the same `SKILL.md` files (the source clone plus the
`.skills` symlink). In-repo / cloud-agent users frequently add a third (a vendored copy at
`.agent-skills/skills/`) that may drift from the source. Agents discovering more than one
copy could load duplicate workflows, merge contradictory instructions, or silently pick the
wrong version. This release fixes that by:

- giving the agent a written, deterministic resolution order it can follow without guessing;
- giving the operator a single config key (`skills.canonical_dir`) that pins the choice;
- giving the agent a small lock file (`.agent-skills.lock`) it can read to detect drift;
- giving the user a first-class update path (`--check-updates` / `--update`) so the
  installed runtime stays close to the source repo.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; existing collaboration handoffs unchanged.
- No new required environment variables. The lock file is gitignored and advisory.
- The `.skills` directory remains a symlink (`--no-symlink` still works). No copy mode
  was added; the supported way to vendor skills is the existing `.agent-skills/skills/`
  pattern documented in `docs/installation.md`.
- `setup.init --update` never pushes, never force-resets, and never auto-runs without the
  flag.

## 0.18.0 - Jira / Confluence Auth Discovery

### Added

- New [`docs/auth-discovery.md`](docs/auth-discovery.md) — the canonical agent-facing
  reference for Jira / Confluence configuration. Defines the explicit discovery order
  (`.agent-skills.yml` → `.jira-config.yml` → `.env` / `.env.local` → process env →
  `scripts/auth-preflight.py` → ask the user), the rules for resolving `${VAR}`
  placeholders, the troubleshooting table for the most common "I can't access Jira"
  failure modes, and the CLI-independent guidance every skill must follow before
  declaring auth unavailable.
- New [`scripts/auth-preflight.py`](scripts/auth-preflight.py) — dependency-free Python
  script that loads `.env`, `.env.local`, and `.jira-config.yml`, resolves `${VAR}`
  placeholders, validates required Jira fields and optional Confluence fields, detects
  API-token-shaped values pasted into `JIRA_PROJECT_KEYS`, and reports the result without
  ever printing a secret value. Exit codes: `0` usable, `1` incomplete, `2` setup error.
  Supports `--require-jira`, `--require-confluence`, `--json`, `--show-prefix`.
- New [`evals/auth-discovery-jira-confluence.md`](evals/auth-discovery-jira-confluence.md)
  — eval scenario for the exact failure mode this release targets: workspace has both
  `.env` and `.jira-config.yml` with placeholders, agent must walk the discovery order
  rather than reporting "no Jira access" and must never echo secret values.
- `eval-runs/v0.18.0/` capturing the auth-discovery scenario and release summary.

### Changed

- `software-engineer`, `issue-investigator`, and `code-reviewer` SKILL.md files now
  carry a mandatory auth-discovery step in their Required Environment section. The
  agent must walk the documented order and run the preflight before reporting Jira /
  Confluence as inaccessible. Unresolved `${VAR}` placeholders in `.jira-config.yml`
  are explicitly classified as **incomplete configuration**, not as missing auth.
- `.env.example` Jira / Confluence sections gained a discovery-contract preamble
  explaining where real values live, where placeholders live, and how to verify
  resolution without exposing secrets.
- `.jira-config.example.yml` placeholder block now states explicitly that `${VAR}`
  placeholders are not expanded by the Jira CLI and points at the auth preflight.
- `.agent-skills.example.yml` `jira:` block links the in-repo discovery order
  (process env → this file → ask the user; no `.env`, no `.jira-config.yml`).
- `scripts/validate-repo.py` adds `check_jira_placeholder_consistency` — fails when
  `.jira-config.example.yml` references a `${VAR}` that is not declared in
  `.env.example`, so the two files cannot drift apart silently.
- `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/installation.md`,
  `docs/configuration.md`, `docs/execution-modes.md`, and `docs/known-limitations.md`
  link the new auth-discovery doc and (where appropriate) the preflight command.

## 0.17.0 - Requirement-Understanding Phase

### Added

- New shared [`docs/requirement-understanding.md`](docs/requirement-understanding.md) workflow
  defining a twelve-step requirement-understanding gate (interpret task, classify, goal,
  expected behavior, actual behavior, scope, evidence, facts/assumptions, unknowns,
  disconfirming checks, confidence, readiness) and the binding confidence-to-action rules every
  relevant skill must apply (`unknown` / `low` blocks implementation, review verdicts, pass/fail
  testing, and automation; `medium` allows planning with visible assumptions; `high` allows
  proceeding within scope).
- New [`docs/requirement-understanding-scorecard.md`](docs/requirement-understanding-scorecard.md)
  scorecard (eleven 0-3 criteria including problem framing, expected behavior clarity, evidence
  discipline, assumption handling, disconfirming checks, readiness decision correctness, and
  resistance to premature implementation).
- New [`docs/examples/requirement-understanding.md`](docs/examples/requirement-understanding.md)
  with six worked examples (clear bug, premature implementation, ambiguous ticket, conflicting
  AC, bug vs feature, security-sensitive request).
- Five new evals targeting the gate:
  [`evals/requirement-understanding-ambiguous-ticket.md`](evals/requirement-understanding-ambiguous-ticket.md),
  [`evals/requirement-understanding-conflicting-criteria.md`](evals/requirement-understanding-conflicting-criteria.md),
  [`evals/requirement-understanding-bug-vs-feature.md`](evals/requirement-understanding-bug-vs-feature.md),
  [`evals/requirement-understanding-wrong-root-cause-trap.md`](evals/requirement-understanding-wrong-root-cause-trap.md),
  [`evals/requirement-understanding-security-sensitive-request.md`](evals/requirement-understanding-security-sensitive-request.md).
- New `Requirement Understanding Gate` step in the Required Workflow of every relevant skill:
  [`software-engineer`](skills/software-engineer/SKILL.md),
  [`issue-investigator`](skills/software-engineer/skills/issue-investigator/SKILL.md),
  [`code-reviewer`](skills/software-engineer/skills/code-reviewer/SKILL.md),
  [`product-owner`](skills/product-owner/SKILL.md),
  [`manual-tester`](skills/manual-tester/SKILL.md),
  [`test-automation-engineer`](skills/test-automation-engineer/SKILL.md). Each gate emits a
  twelve-field `Requirement Understanding` block at the top of skill output, applies the binding
  confidence-to-action rules tailored to that skill, and adds a guardrail forbidding skipping the
  gate.
- `issue-investigator` now tracks **dual confidence** \u2014 root-cause confidence and
  requirement-understanding confidence \u2014 and may not recommend at higher than the lower of the
  two.
- `eval-runs/v0.17.0/` capturing the requirement-understanding multi-skill scenario and release
  summary.

### Changed

- `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/starter-prompts.md`,
  `docs/skill-boundaries.md`, `docs/validation.md`, and `docs/examples/README.md` updated to
  reference the requirement-understanding gate and scorecard.
- `scripts/validate-repo.py` `REQUIRED_FILES` extended with the new docs, evals, and eval-runs.
- `.gitignore` now ignores `.claude/` editor state.

## 0.16.0 - Safety-Acknowledgement Artifact And Credential Blast-Radius Probe

### Added

- New `safety_acknowledgement` block in
  `references/definition-of-done.md` schema. `software-engineer` Phase 5.3
  now writes it whenever the change introduces or performs any mutating
  action against a deployed environment, or touches credentials / IAM /
  secrets / backups / monitoring / network policy. The block captures
  environment, how it was confirmed (a concrete pointer, not a guess),
  the credential used and its source (`host-secret-manager` /
  `env-var` / `user-session`), the blast radius, the execution path
  (`agent` / `ci-pipeline` / `operator-runbook` / `not-applicable`),
  explicit `no_discovered_credentials_invoked` and
  `no_in_repo_tokens_invoked` flags, backup-isolation status, and
  monitoring/IAM/network-policy unchanged flags.
- `code-reviewer` hard handoff contract requires the
  `safety_acknowledgement` block whenever the diff touches a deployed
  environment, credentials, IAM, secrets, backups, monitoring, or
  network policy. The reviewer surfaces a `blocker` finding when the
  block is missing on a diff that obviously requires it, when a
  discovered/in-repo credential was invoked, when a destructive command
  was used without a populated authorization
  (approver + ticket + runbook_path), when `execution_path: agent` for
  a destructive/IAM/secret/backup change, when monitoring/IAM/network
  policy was changed without a written waiver, when `environment:
  production` is paired with `execution_path: agent`, or when
  `backup_restore_tested` is null/older than 90 days for a runbook that
  depends on restore.
- `setup.init` gains a warn-only **credential blast-radius probe** that
  runs at the end of first setup and on `setup.init --verify`. It
  scans the configured `.env` and the current shell for
  destructive-capable cloud / orchestrator / database credentials
  (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
  `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_SERVICE_ACCOUNT_KEY`,
  `AZURE_CLIENT_SECRET`, `DIGITALOCEAN_TOKEN`, `DO_API_TOKEN`,
  `LINODE_TOKEN`, `HCLOUD_TOKEN`, `KUBECONFIG`, `DATABASE_ADMIN_URL`,
  `POSTGRES_ADMIN_PASSWORD`, `MONGODB_ADMIN_URI`, others) and warns the
  operator to scope them to a least-privilege role with no delete-bucket
  / terminate-instance / drop-database / delete-snapshot / IAM-modify /
  backup-mutation privileges. The probe cannot inspect cloud-provider
  IAM policies — it flags the *presence* of broad credentials so the
  operator can confirm scoping in the provider console. Skip with
  `--no-credential-probe`.
- `eval-runs/v0.16.0/` directory with `summary.md` and the
  `safety-ack-and-cred-probe.md` scenario evaluating the new artifact
  and probe against the `v0.15.0` failure-mode chain.

### Changed

- `software-engineer/SKILL.md` Phase 5.3 ("Definition-of-Done artifact")
  has a new checklist item enforcing the `safety_acknowledgement`
  writeback (with the omit-when-not-applicable escape: `applies: false`
  + one-line reason for purely local changes).
- `references/definition-of-done.md` Rules section adds explicit
  reviewer-blocking conditions for the new block, including the
  "missing on a diff that obviously requires it" case (changes to IaC,
  CI deployment, IAM, secret stores, migrations, or any cloud-provider
  command).
- `docs/destructive-action-safety.md` gains an
  "Enforcement artifacts" section documenting the
  `safety_acknowledgement` block and the `setup.init` credential probe
  as the two concrete artifacts that reinforce the policy.
- `setup.init` `--help` and flag parsing add `--no-credential-probe`
  alongside the existing `--no-connectivity-check` flag.
- `VERSION`, README status line, and all six `SKILL.md`
  `metadata.version` values bumped to `0.16.0`.

### Why

`v0.15.0` introduced the destructive-action safety floor as policy +
SKILL content. The two follow-ups in this release operationalise that
policy at two new points:

- The reviewer now has a structured artifact to gate on, not just prose
  in the SKILL.md. A diff that touches a deployed environment cannot
  reach `PASS` without an explicit, machine-checkable acknowledgement
  that the engineer used scoped credentials, did not invoke discovered
  or in-repo tokens, confirmed the environment via a concrete pointer,
  isolated backups, and is not asking the agent itself to execute the
  destructive step.
- The operator now sees a warning at `setup.init` time when the shell
  or `.env` carries credentials that a future agent process would
  inherit and that, combined with the failure mode in `v0.15.0`, would
  let the agent perform destructive cloud operations. The probe is
  warn-only and heuristic; it does not promise to catch every misscope.
  It does promise to surface the most common cases (long-lived AWS
  access keys, broad kubeconfig, admin DB URIs) at a moment when the
  operator can act.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; existing collaboration handoffs unchanged.
- No new required environment variables (the probe reads the existing
  `.env` and the current shell). No `.env.example` change.
- The probe does not block setup, fail CI, or touch state. It is
  intentionally warn-only because IAM scoping cannot be inferred from
  a shell variable name alone.
- The `safety_acknowledgement` block is intentionally optional for
  purely local changes (`applies: false` with a one-line reason) so the
  artifact does not become busywork on docs/refactor/format diffs.

## 0.15.0 - Destructive-Action Safety Floor

### Added

- New top-level policy document `docs/destructive-action-safety.md`
  defining the single source of truth that every skill in this repository
  inherits. Covers: scope and precedence, definitions of "production",
  "destructive action", "discovered credential" vs "authorized credential",
  the prohibited-autonomous-actions hard floor, the read-only-by-construction
  default, the human-controlled-execution contract, the production boundary,
  backup isolation, the discovered-credential protocol, the
  "fix by deletion" anti-pattern, the operator-runbook contract, the
  authorization protocol for legitimate destructive maintenance, and a
  per-skill self-check.
- New `## Destructive Action Guardrails` section in
  `software-engineer/SKILL.md`. Operationalises the policy for engineering
  work: default mode is safe / minimal / non-destructive; never invoke
  discovered credentials; never search the repo *for* credentials in order
  to act; environment must be confirmed (`local`/`dev`/`staging`/
  `production`) before any state-mutating step; destructive commands are
  blocked unless the task is explicitly authorized destructive maintenance
  with a recorded approver, isolated backups, and a human-controlled
  execution path; bug fixing prefers root cause / config / safe migration
  over fix-by-deletion; if the fix appears to require production mutation
  the agent stops and produces a risk-assessed operator runbook instead of
  executing.
- New "Discovered-credential protocol" subsection in
  `issue-investigator/SKILL.md` Step 4: discovered credentials are evidence
  of a leak, not authorization to act; never invoke; never echo full value;
  surface as `blocker`/`major` finding; recommend rotation through the
  organisation's normal channel.
- New "Agent-execution safety (destructive-action policy)" sections in
  `references/code-review-checklist.md` and `references/security-checklist.md`
  with concrete blocker review items: hardcoded secrets, code that invokes
  discovered credentials, destructive cloud / orchestrator / database
  commands targeting production, backup mutation, monitoring-disabling, and
  unconfirmed environment classification.
- `eval-runs/v0.15.0/` directory with `summary.md` and the
  `production-volume-incident.md` scenario evaluating the new floor against
  the documented public failure mode (agent finds a token in the repo and
  uses it to delete production volume / backups).

### Changed

- All six `SKILL.md` files now carry an explicit "Safety floor" callout
  near the top that links to the policy and states the skill-specific
  operational consequences:
  - `software-engineer`: defaults to safe / minimal / non-destructive,
    must not use discovered credentials, must distinguish environments,
    production-impacting actions require human-controlled execution.
  - `issue-investigator`: read-only by default; every proposed check is
    classified `read-only` or `mutating`; mutating checks are not proposed
    by this skill (they belong in a `software-engineer` runbook); never
    asks the user to paste secrets into chat.
  - `code-reviewer`: must surface as `blocker` any diff that ships
    discovered hardcoded secrets, invokes credentials read from repo
    files, runs destructive cloud/orchestrator/db commands against
    production, weakens IAM/network/secret/backup controls, or proposes
    fix-by-deletion of live data — regardless of how the PR description
    frames it.
  - `manual-tester`: tests against deployed environments default to
    read-only / sandbox / ephemeral; discovered credentials are reported
    as `blocker` defects and never invoked; secrets are never pasted into
    chat or test artifacts.
  - `test-automation-engineer`: automated tests must not run destructive
    commands against production; tests that delete/drop/truncate run only
    against ephemeral targets the suite owns and that are isolated from
    any production backup path.
  - `product-owner`: acceptance criteria must not require an agent to run
    destructive production commands, mutate live customer data, modify
    production credentials, or delete backups; such stories must be split
    so the destructive step is an explicit operator runbook handed off
    out of the agent loop.
- `software-engineer/SKILL.md` Stopping Conditions add two new triggers:
  the proposed fix path requires destructive production action, or a
  credential was discovered that is not the agent's authorized credential.
- `issue-investigator/SKILL.md` "Safe read-only checks the user can run":
  every proposed check must now be classified `read-only` or `mutating`
  out loud (indeterminate is treated as `mutating` and not proposed).
  Output contract gains an explicit `Classification:` line.
- `README.md` and `docs/README.md` link to the new policy as a top-level
  reference.
- `scripts/validate-repo.py` REQUIRED_FILES list adds
  `docs/destructive-action-safety.md` so the policy file cannot be
  accidentally removed without breaking CI.

### Why

Production-grade response to a publicly reported failure mode in which an
AI coding agent investigated a problem, discovered a production-capable
token in a checked-in file, used it to call the cloud provider, and caused
the destruction of a production volume and its backups. The failure was
not solely a model lapse — it was the combination of excessive permissions,
in-repo secrets, destructive privileges on the same identity used to read
the codebase, no environment confirmation, no human-controlled execution
boundary, and no backup isolation. Prompt-level "be careful" instructions
are necessary but not load-bearing. After this release, every skill in this
repository inherits the same explicit floor: discovered credentials are
evidence of a leak (never authorization to act), production mutation is a
human-controlled runbook (never an agent invocation), backups are a
separate protected asset, and the floor is not waivable by user prompt.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; existing collaboration handoffs (evidence-pack and
  definition-of-done schemas) are unchanged.
- No new environment variables, no `setup.init` change, no `.env.example`
  change, no CI workflow change beyond the validator REQUIRED_FILES line.
- The four affected SKILLs from `0.14.0` (project-documentation discovery)
  are unchanged in their existing content; they only inherit the new floor.
- `VERSION`, README status line, and all six `SKILL.md` `metadata.version`
  values bumped to `0.15.0`.

## 0.14.0 - Mandatory Project-Docs Discovery (README / CONTRIBUTING / Per-Module README)

### Changed

- `software-engineer/SKILL.md` Phase 1.2 ("Identify the project") now requires
  reading the repository `README.md` and `CONTRIBUTING.md` (and any `docs/`
  setup pages they link to) **before** falling back to the build manifest.
  `${PROJECTS_JSON}` / `.agent-skills.yml` still own the canonical commands,
  but the README is now treated as the source of truth for *prerequisites*
  those commands silently assume (Docker services, fixture generators, env
  vars, profile flags, generated sources, license keys).
- `software-engineer/SKILL.md` Phase 1.2 adds an explicit checklist item for
  **multi-module / nested-submodule repositories**: the agent must read each
  affected module's own `README.md` before invoking that module's build or
  tests. Module-level setup is frequently documented only at the module
  level and is invisible from the parent README or the build manifest. This
  is the most common cause of "tests fail before any change is made"
  reports.
- `software-engineer/SKILL.md` Phase 3.3 ("Build & format") gains two new
  guardrails: a **pre-flight before invoking the test command** that
  verifies README-documented setup has been performed, and a
  **diagnose-before-blame rule** for failing tests on a clean tree (re-read
  README/CONTRIBUTING, check `.github/workflows/` for the exact CI command
  and `services:`/`env:` setup, scan output for missing-prereq signals
  before reporting the suite as broken).
- `issue-investigator/SKILL.md` Step 4 ("Investigate evidence") makes
  project documentation a first-class evidence source: read repository and
  per-module READMEs and `CONTRIBUTING.md` before guessing root cause.
  Documented-but-unmet prerequisites are reclassified from "defect" to
  "environment setup gap".
- `manual-tester/SKILL.md` Step 1 ("Align on intended behavior") requires
  reading repository / per-module READMEs before declaring the environment
  blocked or test data missing — a documented prerequisite is a setup gap,
  not a blocker on the change under test.
- `test-automation-engineer/SKILL.md` Step 3 ("Reuse engineering context")
  requires reading repository, `CONTRIBUTING.md`, and per-module READMEs of
  any module whose tests will be added or changed, so automation matches the
  documented test runner, services, profile flags, and conventions.
- `software-engineer/references/architecture-patterns.md` "Discovering
  project-specific conventions" now leads with README + CONTRIBUTING and
  promotes per-module READMEs to a top-level step, with a short note on why
  CI workflows are also required reading (`services:` / `env:` blocks that
  local docs may omit).

### Why

Production-grade response to a real failure mode: an agent ran tests in a
nested-submodule project, the tests failed because a module-specific test
infrastructure step documented in the per-module README was not performed,
and the agent reported "tests are broken" instead of completing setup. The
README discovery instruction existed only as one line of narrative inside
"Context discovery" and was not present as a hard checklist item in any
phase, nor before the build/test command, nor in the sibling skills. After
this release, the four affected skills (`software-engineer`,
`issue-investigator`, `manual-tester`, `test-automation-engineer`) all
treat repository and per-module documentation as required first-pass
context, and `software-engineer` Phase 3.3 specifically forbids reporting
test failure on a clean tree before the documentation ladder has been
walked.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames or contract changes; evidence-pack and definition-of-done
  schemas are unchanged.
- `code-reviewer` is intentionally not modified — the reviewer consumes the
  engineer's evidence pack and inherits the new discovery discipline through
  the engineer↔reviewer hard handoff contract that was introduced earlier.
- No new environment variables, no `setup.init` changes, no `.env.example`
  changes, no CI changes — pure SKILL content sharpening.
- `VERSION` and all six `SKILL.md` `metadata.version` values bumped to
  `0.14.0`.

## 0.13.0 - Investigator Environment Access, Sonar In Setup, Connectivity Check, Reviewer-Model Clarity

### Added

- `setup.init` learns four new optional flags: `--with-sonar` /
  `--no-sonar` and `--with-environments` / `--no-environments`. Both flows
  also have an interactive opt-in prompt for users who run `setup.init` with
  no flags.
- `setup.init` runs an opt-in non-blocking connectivity probe (`curl --head`,
  5 s timeout) against `JIRA_HOST`, `CONFLUENCE_HOST`, and `SONAR_HOST_URL`
  when those are configured. Any HTTP response (including 401/403) counts
  as reachable; connection errors print a `WARN` and never fail setup.
  Use `--no-connectivity-check` on captive networks / VPNs.
- `SONAR_HOST_URL` and `SONAR_TOKEN` are now setup-managed keys and live
  inside the `# >>> agent-skills setup.init` marker block in `.env`. The
  prior unmanaged placeholders in `.env.example` are removed; the loader's
  "last assignment wins" rule no longer creates silent overrides.
- `ENVIRONMENTS_JSON` is a new optional setup-managed key. It is a JSON
  array of read-only POINTERS (env name, type, access method, ssh target,
  kubectl context, namespace, log paths, log-aggregator URL, notes) to the
  deployed environments where issues actually occur. Credentials are never
  stored — SSH keys stay in `~/.ssh`, cluster credentials in kubeconfig,
  log-aggregator login in the user's session.
- `issue-investigator` SKILL.md gains a new **Environment evidence access**
  subsection that treats `ENVIRONMENTS_JSON` as a first-class evidence
  channel for production and regression issues, with explicit per-access
  read-only command lists (ssh, kubectl, log-aggregator, cloud-console),
  a `propose-do-not-run` default for `type: prod`, and a strict credentials
  boundary. New guardrails forbid running commands against `prod` without
  explicit approval and forbid copying secrets into agent-skills files.
- `issue-investigator` Output Contract now includes an **Environment
  evidence** line under `Evidence Reviewed` so live-environment proof is
  recorded the same way as ticket and code evidence.
- `setup.init --verify` checks `SONAR_HOST_URL`/`SONAR_TOKEN` pairing and
  validates `ENVIRONMENTS_JSON` parses.

### Changed

- `.env.example` rewrites the `CODE_REVIEWER_MODEL` comment block. The
  literal value `"default"` is now documented as a SENTINEL meaning
  "use the host's default model routing." The misleading "uncomment the
  one you want" wording is removed; users are told to *replace the value*
  with one of the listed model ids and given an explicit override example.
- `scripts/validate-repo.py` and the CI smoke test add `SONAR_HOST_URL`,
  `SONAR_TOKEN`, and `ENVIRONMENTS_JSON` to the setup-managed-key list, so
  the marker-block discipline introduced in 0.11.0 also covers the new
  keys.
- `docs/configuration.md` documents the new keys and the `default`
  sentinel for `CODE_REVIEWER_MODEL`.
- `VERSION` and all six `SKILL.md` `metadata.version` values bumped to
  `0.13.0`.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; investigator/code-reviewer/software-engineer hand-off
  contract is unchanged.
- `ENVIRONMENTS_JSON` defaults to `[]`. Users who don't opt in see no
  behavioural change in `issue-investigator`; the existing "Safe read-only
  checks the user can run" path remains the fallback.
- No credentials are introduced into `.env`. Pointers only.

## 0.12.0 - Workspace-Root Prompt Clarity

### Changed

- `setup.init` workspace-root prompt now states explicitly that the answer
  is the **parent folder of your `agent-skills` clone and any sibling repos
  it should manage** (example: `/path/to/work` containing `agent-skills/`,
  `repo-a/`, `repo-b/`). Removes the prior wording that some users read as
  "copy `agent-skills` into a new workspace folder."
- `docs/installation.md` and `docs/quickstart.md` add a one-paragraph
  clarification to the local-workspace section restating the same
  expectation in the same words as the prompt, so prompt and docs no longer
  drift.
- `VERSION` and all `SKILL.md` `metadata.version` values bumped to `0.12.0`.

### Not Changed (deliberate)

- No `SKILL.md` content changed.
- No new top-level or nested skills.
- No changes to setup-managed keys, marker-block discipline, validators, or
  CI behaviour introduced in 0.11.0.

## 0.11.0 - Setup Flow Hardening

### Added

- `setup.init` now prompts with help text that states REQUIRED-WHEN, gives an
  EXAMPLE, and indicates whether a value is optional or whether blank is
  allowed. Secret prompts state explicitly that input is hidden and that the
  value is written only to the gitignored `.env`.
- Auto-population of setup values:
  - `ORG_NAME` is inferred from the Jira host (e.g. `acme.atlassian.net` ->
    `Acme`), then from the GitHub org, then from the workspace root.
  - `ORG_DOMAIN` is inferred from the Jira login email, the Jira host, or the
    GitHub org.
  - The Confluence host is inferred from the Jira host (Atlassian Cloud uses
    `<host>/wiki`; self-hosted `jira.<domain>` becomes `confluence.<domain>`).
  - The Jira project key is extracted from a pasted ticket key (`ABC-123`) or
    ticket URL (`/browse/ABC-123`).
- Optional Confluence configuration: `CONFLUENCE_HOST`, `CONFLUENCE_LOGIN`,
  `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEYS`. New flags
  `--with-confluence` / `--no-confluence` and matching verify output.
- Input validators in `setup.init`: URL shape, email-or-login shape, Jira
  project-key shape, and an explicit rejection of API-token-shaped values
  when project keys are requested.
- `scripts/validate-repo.py` `check_env_example_marker_block`: fails CI if any
  setup-managed key (`ORG_NAME`, `WORKSPACE_ROOT`, `PROJECTS_JSON`, `JIRA_*`,
  `CONFLUENCE_*`) is defined outside the `# >>> agent-skills setup.init` ...
  `# <<< agent-skills setup.init` block in `.env.example`.
- `setup.init --verify` now reports "no duplicate managed keys" and "Confluence
  credentials present" when applicable.
- `eval-runs/v0.11.0/` with the release summary and the
  `setup-flow-hardening.md` scenario.

### Changed

- `.env.example` restructured so every setup-managed key lives inside the
  marker block. Non-managed keys (code-reviewer overrides, build tooling
  hints, etc.) remain outside the block and are preserved across reruns.
- `setup.init` strips legacy duplicate setup-managed keys defined outside the
  marker block during a one-time migration on rerun, reporting how many
  duplicates it removed.
- `setup.init` sets `chmod 600` on generated `.env` and `.jira-config.yml`.
- `.agent-skills.example.yml` now documents `org_domain`, the optional
  `confluence` block, and richer Jira metadata (`project_keys`, `login`,
  `auth_type`). Secrets are still injected via host environment variables.
- `docs/configuration.md`, `docs/installation.md`, `docs/quickstart.md`, and
  `docs/execution-modes.md` updated for the new managed-block discipline,
  Confluence support, and inference behaviour.
- CI workflow exercises a `--with-confluence` non-interactive flow and
  asserts no duplicate managed keys appear in `.env` after rerun.
- `VERSION` and all `SKILL.md` `metadata.version` values bumped to `0.11.0`.

### Fixed

- Root cause of duplicated `PROJECTS_JSON`, `JIRA_HOST`, `JIRA_API_TOKEN`,
  `JIRA_LOGIN`, and `JIRA_PROJECT_KEYS` keys in `.env`: the previous
  `.env.example` contained literal definitions of those keys outside the
  generated marker block, so copying the example and then writing the
  generated block produced two definitions per key. The example now keeps
  exactly one definition per key, inside the block.
- `setup.init` no longer renders an empty `JIRA_*` block when Jira is
  declined; it emits explicit empty assignments inside the marker block so
  the variables are always defined and the order is deterministic.

### Not Changed (deliberate)

- No `SKILL.md` content changed.
- No new top-level or nested skills.
- No changes to the eval scoring rubric.
- Local-workspace and in-repo modes remain the only two supported execution
  modes.

### Security

- Secrets (Jira API token, Confluence API token) are read with hidden input
  and never echoed.
- Generated files containing or potentially containing secrets are written
  with `0600` permissions.
- Workspace `.gitignore` continues to ignore `.env`, `.env.local`,
  `.env.*.local`, `.jira-config.yml`, `.skills`, and `.cache/`.
- Examples and templates use `acme.example.com` / `example.org` placeholders
  only.

## 0.10.0 - Eval-Driven Skill Improvements

### Added

- `code-reviewer` workflow step "Record review limitations explicitly" plus a
  matching `Review Limitations / Unavailable Context` section in the output
  contract. A bare `PASS` verdict is now disallowed while review-limitation
  items are non-`none`.
- `issue-investigator` workflow subsection "Safe read-only checks the user
  can run" plus a matching `Safe Checks The User Can Run` block in the output
  contract. Each suggested check must be read-only by construction, bounded,
  labelled with the safe environment, and tied to a specific hypothesis.
- Two deeper eval scenarios under `evals/` exercising realistic incomplete
  context: `issue-investigator-read-only-investigation.md` and
  `code-reviewer-unavailable-context.md`.
- `eval-runs/v0.10.0/` with the matching scored runs and a release summary.
- Three explicit eval-run categories in `eval-runs/README.md` (illustrative,
  real model transcript, future automated). Every new eval-run file must
  declare its category.

### Changed

- `code-reviewer` and `issue-investigator` behavior checklists updated to
  require the new sections to be filled.
- `issue-investigator` guardrails extended to forbid mutating or unbounded
  checks being labelled "safe".
- Updated `VERSION`, README status, and all skill metadata to `0.10.0`.
- Validator `REQUIRED_FILES` extended to require the new eval scenarios and
  the v0.10.0 eval-run files.

### Not Changed (deliberate)

- No new skills.
- No nested skill promoted to the top level.
- Skill philosophy was not rewritten. The two skill changes are wording-level
  additions that the v0.9.0 eval runs explicitly recommended as future work.
- No real model transcripts captured this release; the category exists but
  populating it is a future-release task.
- Eval runs still do not gate CI.

## 0.9.0 - Real Eval Runs and Scored Skill Outputs

### Added

- `eval-runs/` directory with a release-scoped subdirectory `eval-runs/v0.9.0/`
  containing scored sample runs for each skill plus a multi-skill chained flow.
- A summary file aggregating per-skill scores, common strengths, common gaps,
  and follow-up actions.
- An `eval-runs/README.md` that describes the practice, scoring method, and
  public-safety rules, and clearly labels the v0.9.0 transcripts as
  illustrative maintainer-authored examples.

### Changed

- `docs/validation.md`, `docs/release-checklist.md`, and
  `docs/skill-performance-review.md` now reference eval-runs as the maintainer
  evidence trail.
- `README.md` documentation index links to `eval-runs/`.
- Updated `VERSION`, README status, and all skill metadata to `0.9.0`.
- Validator `REQUIRED_FILES` extended to ensure the v0.9.0 eval-run files exist.

### Not Changed (deliberate)

- No new skills added.
- No nested skill promoted to the top level.
- Skill wording was not rewritten purely to chase higher eval scores; gaps
  surfaced during eval runs are recorded for future releases.

## 0.8.2 - Physical Source Formatting Fix

### Changed

- Replaced remaining wide Markdown tables in `README.md`,
  `docs/skill-performance-review.md`, `skills/software-engineer/SKILL.md`, and
  `skills/software-engineer/skills/issue-investigator/SKILL.md` with readable
  per-item sections so no Markdown line exceeds the new 200-character limit.
- Updated `VERSION`, README status, skill metadata, and release checklist for
  `0.8.2`.

### Fixed

- Tightened `scripts/validate-repo.py` line-length limits to 200 characters for
  Markdown and source files and lowered the source long-line warning threshold
  to 140 characters.
- Added a Markdown file-density check that fails files where the byte-per-line
  ratio shows the file is physically compressed.
- Added a YAML minification check that fails when multiple top-level keys
  collapse onto one physical line or when inline flow values look minified.
- Added a Python minification check that fails on multiple statements per line.

## 0.8.1 - Source Formatting and Release Hygiene

### Changed

- Reformatted Markdown bodies across the README, changelog, docs, evals, skill files, and support
  docs so raw GitHub view and Git diffs remain readable.
- Reformatted `SKILL.md` YAML frontmatter to use folded scalars for long descriptions and
  compatibility text.
- Replaced overwide Markdown tables in docs and skill environment sections with readable lists where
  table rows made raw source hard to review.
- Updated `VERSION`, README status, and skill metadata for `0.8.1`.

### Fixed

- Moved the v0.8.0 validation/evaluation entries out of `Unreleased` into the released v0.8.0
  changelog section.
- Strengthened `scripts/validate-repo.py` so CI fails on maintainability issues such as overlong
  Markdown lines, mid-line headings, collapsed table rows, and mid-line code fences.
- Added readability checks for YAML and Python source lines.
- Updated the release checklist with raw README, table-rendering, changelog hygiene, and validator
  line-readability checks.

## 0.8.0 - Validation, Evaluation, and Skill Performance Hardening

### Added

- **`scripts/validate-repo.py`** for repository-wide validation of required files, Markdown
  structure, balanced code fences, internal relative links, skill frontmatter, required skill
  sections, version consistency, cross-skill links, forbidden public-safety content, and tracked
  generated/cache files.
- **`docs/validation.md`** explaining what validation checks, what it does not check, how to run it,
  and how to interpret warnings vs failures.
- **`evals/`** with lightweight manual scenarios for `issue-investigator`, `code-reviewer`,
  `software-engineer`, `product-owner`, `manual-tester`, `test-automation-engineer`, and a multi-skill
  bug-to-regression workflow.
- **`docs/skill-quality-scorecard.md`** with a simple `0` to `3` maintainer scoring aid for skill
  outputs across context awareness, evidence discipline, handoffs, output completeness, hallucination
  avoidance, validation realism, risk awareness, stopping behavior, and portability.
- **`docs/skill-performance-review.md`** recording the v0.8.0 manual review findings and the
  workflow checks for bug fix, feature delivery, and PR review paths.
- **`docs/release-checklist.md`** covering validation, README rendering, skill links, changelog and
  version updates, examples/evals, secrets/private-reference review, GitHub release notes, tags, and
  funding-link rendering.

### Changed

- Updated CI to run the broader repository validator instead of only skill frontmatter checks.
- Kept `scripts/validate_skills.py` as a backward-compatible wrapper around the repository
  validator.
- Added behavior checklists to all six skills so expected behavior can be reviewed independently of
  the longer workflows.
- Bumped `VERSION`, README status, and all skill metadata versions to `0.8.0`.
- Generalized `software-engineer` issue-source wording so non-Jira issue sources and supplied task
  briefs are handled without implying a private workflow.
- Clarified `product-owner` behavior for bug-flavored input: unknown-root-cause work should become
  investigation/discovery, not a fix-ready story.
- Aligned `issue-investigator` and `code-reviewer` execution-mode detection with
  `AGENT_SKILLS_MODE`.
- Softened the `test-automation-engineer` flake-budget rule into a default target with a disclosed
  fallback when CI/tooling cannot support repeat execution.

### Guardrails

- Validation now fails on likely committed secrets, private absolute paths, missing required skill
  structure, malformed metadata, broken relative links, and version mismatches.
- Validation warns on suspicious hostnames, possible real email/customer data, hardcoded ticket
  keys, README/version drift, and local generated/cache files that lack ignore coverage.
- Documentation explicitly states that validation and scorecards do not guarantee AI model
  correctness.

## 0.7.0 - Skill Output Contracts, Examples, and Operational Behavior Hardening

### Added

- **Expected output contracts for all six skills** so agents produce predictable summaries,
  evidence, validation notes, handoffs, and final status/verdict fields.
- **`docs/examples/`** with one realistic, portable example per skill covering input prompt,
  assumed context, expected behavior, sample output structure, and what to avoid.
- **`docs/starter-prompts.md`** with copy-paste prompts for each skill plus multi-skill workflows
  (`product-owner -> software-engineer -> manual-tester -> test-automation-engineer`,
  `issue-investigator -> software-engineer -> code-reviewer`, and `manual-tester defect ->
  issue-investigator -> test-automation-engineer`).
- **`docs/skill-boundaries.md`** documenting role ownership, handoff rules, nested support-skill
  rationale, and possible future top-level criteria for `issue-investigator` and `code-reviewer`.
- **`docs/severity-and-confidence.md`** defining `blocker`, `major`, `minor`, `nit`,
  `low`/`medium`/`high` confidence, and issue-investigator root-cause statuses (`unknown`,
  `suspected`, `confirmed`, `disproved`).
- **`docs/README.md`** as a documentation index for quickstart, prompts, examples, boundaries,
  severity/confidence, limitations, and versioning.

### Changed

- Hardened all skill docs with explicit `When Not To Use` and `Stopping Conditions` sections where
  they were missing.
- Made cross-skill reuse rules explicit: engineering invokes investigation for unclear issues and
  review at gates; review invokes investigation when ticket/root-cause context is weak; manual testing
  hands reproducible defects to investigation; automation consumes stable manual/repro scenarios;
  product ownership routes bug-flavored input through investigation.
- Updated `code-reviewer` verdicts to `PASS`, `PASS_WITH_NOTES`, `REQUEST_CHANGES`,
  `NEEDS_CONTEXT`, and `NOT_REVIEWABLE`.
- Aligned public docs and skill metadata with release `0.7.0`.

### Guardrails

- Reinforced public usability disclaimers across skills: do not invent evidence, distinguish facts
  from assumptions, stop when context is insufficient, do not claim tests were run unless actually
  run, do not confirm root cause without evidence, and do not assume private company standards.

## 0.6.1 - Documentation Rendering and Public Usability Fixes

### Added

- **`docs/quickstart.md`** — short first-time user path covering what the repository is, when to use
  it, how to invoke one skill manually, both execution modes, and starter prompts for the four
  top-level skills.
- **`docs/known-limitations.md`** — public limitations for non-deterministic agent behavior,
  nested-skill support, external access, company-specific standards, human review, cache behavior, and
  no-warranty/no-SLA expectations.
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
  Holds the single `project:` block and the org/github/jira-host metadata previously read from `.env`.
  Contains **no secrets**; credentials still come from environment variables injected by the host
  platform.
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
  and `repro-recipe.yml`. Cached at `${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/`. Defines what
  each skill reads and writes so `issue-investigator`, `software-engineer`, `code-reviewer`,
  `manual-tester`, `test-automation-engineer`, and `product-owner` stop re-deriving context on every
  hop.
- **`skills/software-engineer/references/definition-of-done.md`** — the schema for
  `definition-of-done.json`, the Phase 5 gate artifact the reviewer must verify before declaring
  `PASS`. Includes bug-fix-specific fields (regression-test commit, fails-on-parent, passes-on-head,
  observability_added) and operational hygiene flags (`no_no_verify`, `branch_starts_with_ticket_key`,
  `no_unrelated_files`).
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
  engineering work, shared as a public good. Issues and PRs are not actively solicited; forking is the
  recommended path for divergent needs. The new files set realistic expectations up front instead of
  implying a contributor pipeline that does not exist.
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
  (project entry, issue brief, root-cause confidence, failing-test commit for bug fixes, 5-line plan,
  risk areas). Missing handoff is a `major` finding.
- **`code-reviewer` `test-quality` review profile** for `manual` mode when reviewing test code
  (selector stability, deterministic data, condition-based waits, assertion meaningfulness,
  isolation).
- **`code-reviewer` iteration convergence rule (`CODE_REVIEWER_MAX_ROUNDS`, default `3`).**
  Blocker+major finding count must strictly decrease between rounds; non-converging loops escalate to
  the user instead of grinding indefinitely or silently downgrading blockers.
- **`code-reviewer` devil's-advocate self-rebuttal** before any `PASS` verdict, attacking your own
  conclusion against silent data loss, lost-update / race conditions, auth bypass, secret/PII leakage,
  broken migration, breaking API contract, and regression risk.
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
  `setup.init --yes` and `--verify` end-to-end against a temp git workspace (including idempotency and
  `$HOME`-refusal assertions), and runs a markdown link check.
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
  creates or refreshes `.env`, `.jira-config.yml` (optional), the `.skills` symlink, and an idempotent
  agent-skills block in the workspace `.gitignore`.
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
  `.jira-config.yml`, `.skills`, and `.cache/` so workspaces that are themselves git repos do not show
  those files as uncommitted changes (and `.env` does not risk leaking secrets). Idempotent on rerun.

### Documentation

- CONTRIBUTING.md documents the `setup.init` validation expectation for contributors.

## 0.1.0 - Initial Public Baseline

- Added the initial `software-engineer` role skill.
- Added nested review and Jira-driven issue resolution skills under `software-engineer`.
- Added reference checklists for code review, security, SonarQube-style quality gates, and
  architecture patterns.
- Added environment and Jira configuration templates.
