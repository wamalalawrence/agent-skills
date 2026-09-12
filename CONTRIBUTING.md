# Contributing

This is a **solo-maintained project, not open to outside contribution**. Its source is readable,
but it is not open source and is not distributed for outside use. This file is the internal bar
for a change — for the maintainer and anyone explicitly invited to the repository.

## Ground rules

- Land every change through a pull request on a short-lived branch. `main` is protected.
- `python3 scripts/validate-repo.py` must pass before a PR is opened.
- Update `CHANGELOG.md` under `## Unreleased` for anything that affects behaviour, structure,
  setup, or skill invocation.
- No new runtime dependency, install step, or required environment variable without a written
  decision recorded in `docs/` or the changelog.

## Bar for a change

- **No hardcoded org, repo, server, host, token, or local path** in any `SKILL.md` or reference
  file. Use `${ENV_VAR}` references and add the variable to [`.env.example`](./.env.example).
- **Skills compose, they do not duplicate.** Reference another skill by relative path; do not copy
  its content.
- Checklists (`- [ ]`) for anything an agent should tick through.
- Fenced code blocks with language tags. ASCII unless the surrounding file already uses
  non-ASCII. Workspace-relative Markdown links between files.

## Validation

```bash
python3 scripts/validate-repo.py                  # must pass
bash scripts/test-tools.sh                         # if you touched the tool framework
bash scripts/test-guard.sh                         # if you touched Execution Guard
bash scripts/test-context-optimizer.sh             # if you touched Context Optimizer
bash scripts/test-access-resolution.sh             # if you touched the Access Resolver
python3 scripts/test-access-discovery.py           # if you touched Access Discovery (scripts/access_*.py)
bash scripts/test-cli-install.sh                   # if you touched installation
python3 scripts/test-release-engine.py             # if you touched the release engine
node scripts/test-release-signing.js               # if you touched signing, the verifier, or the bootstrap
bash scripts/test-knowledge.sh                     # if you touched the memory tiers, durable.py, or the lifecycle wrappers
bash scripts/test-secret-boundary.sh               # if you touched anything that writes durable state
python3 scripts/test-meeting.py                    # if you touched Meeting Intelligence (scripts/meeting*.py)
```

Before tagging a release, work through [docs/release-checklist.md](docs/release-checklist.md) and
run `bash scripts/test-release-readiness.sh`.
