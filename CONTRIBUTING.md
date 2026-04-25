# Contributing to agent-skills

Thank you for considering a contribution. This project is meant to provide reusable public-good engineering resources, so the most valuable contributions are clear, portable, practical, and easy for another maintainer to validate.

This is currently a solo-maintainer project. Reviews are best effort, and small focused changes are much easier to accept than broad rewrites.

## Good Contributions

- Fix portability problems in a skill or template.
- Clarify confusing instructions without making the skill longer than it needs to be.
- Improve checklists with concrete, broadly applicable engineering guidance.
- Add realistic examples that use neutral placeholder values.
- Propose a new role or nested skill after showing why the current structure cannot cover it.

## Golden Rules

1. **No hardcoded org, repo, server, host, token, or local path** in any `SKILL.md` or reference file. Use `${ENV_VAR}` references and add the variable to [`.env.example`](./.env.example).
2. **Fail fast on missing context.** If a skill needs an env var or input such as a Jira ticket, repo path, issue description, or target branch, stop and tell the user exactly what to provide.
3. **Use real context, not invented context.** Skills should prefer tickets, linked docs, repository conventions, CI workflows, tests, and current code over assumptions.
4. **Cache remote fetches where appropriate.** Jira, Confluence, GitHub API, and similar calls should use a cache directory and TTL from `.env` so repeated runs stay fast and token-efficient.
5. **Skills compose, they do not duplicate.** If a skill needs another skill's behavior, reference it by relative path instead of copying its contents.
6. **Keep the main skill readable.** Aim for under roughly 400 lines in `SKILL.md`; push long checklists and examples into `references/`.

## Project Structure

Top-level role skills live under `skills/<role>/`. Nested specializations for a role live under `skills/<role>/skills/<nested-skill>/`.

```text
skills/<role>/
├── SKILL.md
├── README.md
├── references/
└── skills/
    └── <nested-skill>/
        ├── SKILL.md
        └── README.md
```

Do not create a new top-level role just because a concern exists. For example, `code-reviewer` and `issue-investigator` are currently nested under `software-engineer` because review, implementation, issue investigation, and issue resolution are part of one engineering workflow.

## Adding Or Changing A Skill

`SKILL.md` frontmatter must include:

```yaml
---
name: <skill-name>
description: 'Use when: ... Explain when the skill applies, what it produces, and what context or dependencies it uses.'
---
```

Recommended sections, in order:

1. **Required Environment**: every env var the skill needs, whether it is required or optional, and what happens when it is missing.
2. **Context Discovery**: how the skill gathers issue, project, repository, and user context.
3. **Required Inputs**: what the user must provide or what the skill may derive.
4. **Workflow**: numbered phases the skill walks through.
5. **Output Format**: what the user gets at the end.
6. **Non-Negotiable Rules**: what the skill will never do.

## Testing A Change

There is no automated test harness yet. Before opening a PR:

1. Run a realistic task end to end with the edited skill in your own workspace.
2. Temporarily blank out one required env var and confirm the skill stops with a clear, actionable message.
3. Check that no organization-specific strings were introduced inside `skills/`:

```bash
grep -RE "(https?://[^$]|github\.com/[^$]|@[A-Za-z0-9._%+-]+\.[A-Za-z]{2,}|acme|cubic)" skills/
```

4. Check that any new environment variable is documented in [`.env.example`](./.env.example).
5. Update [CHANGELOG.md](./CHANGELOG.md) when the change affects public behavior, documented structure, or skill invocation.

## Pull Request Expectations

- Keep PRs focused on one problem.
- Explain what changed, why it matters, and how it was validated.
- Link issues when available.
- Call out any breaking changes to skill names, folder layout, required inputs, or required environment variables.
- Accept that the maintainer may choose a smaller version of the idea to keep the project simple.

## Style

- Markdown only.
- Use checklists (`- [ ]`) for anything the agent should tick through.
- Use fenced code blocks with language tags for commands or structured examples.
- Prefer ASCII unless the surrounding file already relies on non-ASCII notation.
- Reference other files with workspace-relative markdown links.
