# Changelog

All notable project changes should be recorded here.

## Unreleased

## 0.2.0 - Onboarding And Positioning

### Added
- `setup.init`: bash automation for first-run workspace setup. Asks a short set of questions, then creates or refreshes `.env`, `.jira-config.yml` (optional), the `.skills` symlink, and an idempotent agent-skills block in the workspace `.gitignore`.
- `setup.init --verify`: re-checks an existing setup without writing — required env vars, `PROJECTS_JSON` shape, every project path resolves, `.skills` target valid, Jira credentials consistent.
- "Why Skills" section in the README explaining how a skill turns a generalist LLM into a specialist (general practitioner vs. dentist analogy).
- "Try A First Prompt" section in the README with one starter prompt per skill.
- Honest "Using With Your AI Assistant" compatibility table covering Claude Code, Cursor/Windsurf/Continue, GitHub Copilot Chat, and generic chat clients.

### Changed
- README Quick Start now leads with `./setup.init` and an explicit recommended workspace layout, with manual `cp` setup retained as a fallback.
- `.env.example` headers point at `setup.init` and ship safer bootstrap defaults.
- Nested `code-reviewer` README clarifies that `CODE_REVIEWER_MODEL` is optional, not required.

### Hardened
- `setup.init` refuses unsafe workspace roots (`$HOME`, `/`, and common system directories) so a fresh clone in the wrong place cannot pollute your shell environment. Explicit `--workspace-root` requires interactive confirmation to override.
- JSON validation prefers `python3` (universally present), falls back to `ruby`, and only skips with a warning when neither is installed.
- `GITHUB_ORG` is detected from sibling repository `remote.origin.url` first, then falls back to `gh api user --jq .login`, then leaves the field blank.
- Build and format commands are inferred per package manager: `pnpm`/`yarn`/`bun`/`npm` lockfiles plus `package.json` script presence; Poetry-aware Python; gradle fallback when no wrapper is present.
- The generated `.env` block carries an explicit warning that contents inside the markers are overwritten on rerun and that manual edits belong outside the markers.
- The generated workspace `.gitignore` block covers `.env`, `.env.local`, `.env.*.local`, `.jira-config.yml`, `.skills`, and `.cache/` so workspaces that are themselves git repos do not show those files as uncommitted changes (and `.env` does not risk leaking secrets). Idempotent on rerun.

### Documentation
- CONTRIBUTING.md documents the `setup.init` validation expectation for contributors.

## 0.1.0 - Initial Public Baseline

- Added the initial `software-engineer` role skill.
- Added nested review and Jira-driven issue resolution skills under `software-engineer`.
- Added reference checklists for code review, security, SonarQube-style quality gates, and architecture patterns.
- Added environment and Jira configuration templates.