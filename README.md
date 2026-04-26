# agent-skills

Reusable [Agent Skills](https://agentskills.io/) for software-engineering work — portable,
role-shaped workflows your AI assistant can load on demand so the same model produces
senior-engineer, product-owner, tester, or reviewer output instead of generic answers.

> **Status:** `0.8.1` — pre-1.0. Core skill set is shipped and stable enough for public use;
> interfaces may still evolve.

New here? Start with the [quickstart](docs/quickstart.md), then read [starter
prompts](docs/starter-prompts.md), [examples](docs/examples/README.md),
[validation](docs/validation.md), [known limitations](docs/known-limitations.md), and the
[versioning policy](docs/versioning.md).

## Why Skills

A general-purpose LLM is a general practitioner: capable, broad, but not specialized. A skill turns
that same model into a specialist for a narrow, high-value task — with the right context, the right
checklist, and the right stopping conditions.

- **Without a skill:** you ask "fix this bug" and hope the model remembers your standards.
- **With a skill:** the model follows a tested workflow — gather just enough evidence, propose a
  safe plan, implement, self-review, and stop when context is missing instead of guessing.

## Install

`agent-skills` runs in two execution modes — pick the one that matches **where the agent actually
runs**. Full comparison in [docs/execution-modes.md](docs/execution-modes.md).

### Local workspace (your laptop, multiple repos)

For Claude Code, Cursor, Windsurf, Continue, GitHub Copilot Chat in VS Code/JetBrains, or any local
assistant working across several sibling repos:

```bash
git clone https://github.com/wamalalawrence/agent-skills.git
cd agent-skills
./setup.init
```

`setup.init` writes `.env`, optional `.jira-config.yml`, a `.skills` symlink, and a `.gitignore`
block into the parent workspace folder. See [docs/installation.md](docs/installation.md) for the
workspace layout, all flags, and manual setup.

### In-repo (online / cloud agents, single repository)

For GitHub Copilot coding agent (github.com), Cursor cloud / background agents, Devin, Codex, GitHub
Codespaces, Gitpod, or ChatGPT/Claude on the web with the repo attached — anywhere there is no local
workspace folder:

1. Copy [`.agent-skills.example.yml`](.agent-skills.example.yml) to `.agent-skills.yml` at the
  **target repository's** root and fill in the `project:` block. No secrets in this file.
2. Vendor the `skills/` folder you want to use into the target repo (copy or `git submodule add`),
  or reference specific `SKILL.md` files from your agent's instruction surface
  (`.github/copilot-instructions.md`, `.cursor/rules/`, project-attached files, …).
3. Add `.cache/` to the target repo's `.gitignore`.
4. Inject any required secrets (`JIRA_API_TOKEN`, `GITHUB_TOKEN`, …) via the host platform's secret
  mechanism.

See [docs/installation.md](docs/installation.md) and [docs/assistants.md](docs/assistants.md) for
per-platform details.

### Or — install just the skills via the [Agent Skills](https://skills.sh) ecosystem

```bash
npx skills add wamalalawrence/agent-skills
```

## Skills

This repository currently contains **four top-level skills** and **two nested support skills**. The
top-level skills are intended to be invoked directly. The nested support skills are loaded by the
engineering workflow when investigation or review needs a more specific checklist.

`issue-investigator` and `code-reviewer` are currently nested under `software-engineer` because they
support the engineering implementation loop. They may become top-level skills later only if real
usage shows they are useful independently.

| Skill                                      | Role                 | Key collaborators                                                     | Purpose                                                                                       |
| ------------------------------------------ | -------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [`software-engineer`][software-engineer]   | Top-level skill      | `product-owner`, `manual-tester`, `test-automation-engineer`          | End-to-end engineering: context discovery, implementation, QA, self-review, PR preparation.   |
| [`product-owner`][product-owner]           | Top-level skill      | `software-engineer`, `manual-tester`, `test-automation-engineer`      | Clarifies goals, requirements, scope, acceptance criteria, UX concerns, and handoff notes.    |
| [`manual-tester`][manual-tester]           | Top-level skill      | `product-owner`, `software-engineer`, `test-automation-engineer`      | Plans and executes manual validation, exploratory testing, defect reporting, retest guidance. |
| [`test-automation-engineer`][tae]          | Top-level skill      | `software-engineer`, `manual-tester`, `product-owner`                 | Designs stable automated tests at the right level and prevents brittle automation.            |
| [`issue-investigator`][issue-investigator] | Nested support skill | `software-engineer`, `manual-tester`, `product-owner`                 | Builds issue evidence, reproduction steps, root-cause status, and handoff.                    |
| [`code-reviewer`][code-reviewer]           | Nested support skill | `software-engineer`, `test-automation-engineer`, `issue-investigator` | Reviews diffs against issue context, evidence packs, quality risks, and definition of done.   |

[software-engineer]: skills/software-engineer/
[product-owner]: skills/product-owner/
[manual-tester]: skills/manual-tester/
[tae]: skills/test-automation-engineer/
[issue-investigator]: skills/software-engineer/skills/issue-investigator/
[code-reviewer]: skills/software-engineer/skills/code-reviewer/

## Documentation

- [Docs index](docs/README.md)
- [First-time user quickstart](docs/quickstart.md)
- [Installation & `setup.init`](docs/installation.md)
- [Configuration & multi-project workspaces](docs/configuration.md)
- [Using with your AI assistant](docs/assistants.md)
- [Starter prompts](docs/starter-prompts.md)
- [Examples](docs/examples/README.md)
- [Validation](docs/validation.md)
- [Skill quality scorecard](docs/skill-quality-scorecard.md)
- [Skill performance review](docs/skill-performance-review.md)
- [Release checklist](docs/release-checklist.md)
- [Skill boundaries](docs/skill-boundaries.md)
- [Severity and confidence definitions](docs/severity-and-confidence.md)
- [Known limitations](docs/known-limitations.md)
- [Versioning policy](docs/versioning.md)
- [Roadmap](ROADMAP.md) · [Support](SUPPORT.md) · [Governance](GOVERNANCE.md) ·
  [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

## Design Principles

- **Portable:** no company names, hostnames, tokens, repository names, or local paths inside skill
  files.
- **Context-aware:** skills use issue context, linked docs, repository conventions, tests, and CI
  signals before recommending changes.
- **Token-conscious:** gather the smallest useful evidence pack first, then expand only when
  ambiguous or high risk.
- **Collaborative:** implementation, review, and issue resolution are one engineering loop, not
  isolated activities.
- **Maintainer-realistic:** governance, support, and roadmap promises match a solo-maintainer
  open-source project.

## Contributing

This is a solo-maintained project I built for my own engineering work and shared as a public good.
**Issues and PRs are not actively solicited.** I may not respond, may close work that doesn't fit
the project's direction, and reserve the right to keep the scope small.

If you still want to send something, the bar is in [CONTRIBUTING.md](CONTRIBUTING.md): focused,
portable, and easy for one person to verify in an evening. Forking is a perfectly fine alternative
if your needs diverge.

## License

[MIT](LICENSE).
