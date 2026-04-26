# Contributing

This is a solo-maintained project. I built `agent-skills` for my own engineering work and publish it
as a public good — not as an attempt to grow a community, accept feature requests, or onboard
co-maintainers.

**Please read this before opening anything:**

- I will not necessarily respond to issues or PRs.
- I may close contributions without detailed feedback if they don't fit the project's direction or
  would expand scope I'm not willing to maintain.
- There is no roadmap-by-committee, no triage SLA, no review queue.
- **If you need something different, fork it.** That is the cleanest path and it's MIT licensed
  precisely so you can.

If you still want to send a small focused improvement, the rules below are the bar.

## Acceptable Changes

- Fix a portability problem (hardcoded org/host/path/token leaking into a `SKILL.md` or template).
- Fix a typo, broken link, or a clearly wrong instruction.
- Tighten an existing checklist with a concrete, broadly-applicable engineering item.
- Improve a reference checklist with neutral, public-domain guidance.

## Out of Scope

- New top-level roles, new nested skills, or large rewrites — open an issue first to ask, and accept
  that the answer may be "no".
- Features that exist mainly to support a specific company, stack, or workflow that isn't broadly
  portable.
- Adding new required environment variables, new install paths, or new dependencies without prior
  agreement.
- Anything that would meaningfully expand my maintenance load.

## Hard Rules (PRs that violate these will be closed)

1. **No hardcoded org, repo, server, host, token, or local path** in any `SKILL.md` or reference
   file. Use `${ENV_VAR}` references and add the variable to [`.env.example`](./.env.example).
2. **Skills compose, they do not duplicate.** Reference another skill by relative path; do not copy
   its content.
3. **Run `python3 scripts/validate-repo.py`** locally — it must pass.
4. **Update `CHANGELOG.md`** under `## Unreleased` if your change affects public behavior,
   structure, setup, or skill invocation.
5. **No new dependencies, no new install steps, no new required env vars** without prior issue
   discussion.

## Validation

Before opening a PR:

```bash
python3 scripts/validate-repo.py                  # must pass
./setup.init --yes --no-jira --workspace-root $(mktemp -d)  # if you touched setup
grep -RE "(https?://[^$]|github\.com/[^$]|@[A-Za-z0-9._%+-]+\.[A-Za-z]{2,})" skills/  # no leaked URLs/handles in skills/
```

## Style

- Markdown only.
- Checklists (`- [ ]`) for anything the agent should tick through.
- Fenced code blocks with language tags.
- ASCII unless the surrounding file already uses non-ASCII.
- Workspace-relative markdown links to other files.

## Why so terse?

Project documentation that _sounds_ welcoming while a single maintainer ignores most contributions
wastes everyone's time. This file is meant to set realistic expectations up front so neither of us
is disappointed.
