# agent-skills

Reusable [Agent Skills](https://agentskills.io/) for software-engineering work — portable, role-shaped workflows your AI assistant can load on demand so the same model produces senior-engineer, product-owner, tester, or reviewer output instead of generic answers.

> **Status:** `0.6.0` — pre-1.0. Core skill set is shipped and stable enough for public use; interfaces may still evolve.

## Why Skills

A general-purpose LLM is a general practitioner: capable, broad, but not specialized. A skill turns that same model into a specialist for a narrow, high-value task — with the right context, the right checklist, and the right stopping conditions.

- **Without a skill:** you ask "fix this bug" and hope the model remembers your standards.
- **With a skill:** the model follows a tested workflow — gather just enough evidence, propose a safe plan, implement, self-review, and stop when context is missing instead of guessing.

## Install

`agent-skills` runs in two execution modes — pick the one that matches **where the agent actually runs**. Full comparison in [docs/execution-modes.md](docs/execution-modes.md).

### Local workspace (your laptop, multiple repos)

For Claude Code, Cursor, Windsurf, Continue, GitHub Copilot Chat in VS Code/JetBrains, or any local assistant working across several sibling repos:

```bash
git clone https://github.com/wamalalawrence/agent-skills.git
cd agent-skills
./setup.init
```

`setup.init` writes `.env`, optional `.jira-config.yml`, a `.skills` symlink, and a `.gitignore` block into the parent workspace folder. See [docs/installation.md](docs/installation.md) for the workspace layout, all flags, and manual setup.

### In-repo (online / cloud agents, single repository)

For GitHub Copilot coding agent (github.com), Cursor cloud / background agents, Devin, Codex, GitHub Codespaces, Gitpod, or ChatGPT/Claude on the web with the repo attached — anywhere there is no local workspace folder:

1. Copy [`.agent-skills.example.yml`](.agent-skills.example.yml) to `.agent-skills.yml` at the **target repository's** root and fill in the `project:` block. No secrets in this file.
2. Vendor the `skills/` folder you want to use into the target repo (copy or `git submodule add`), or reference specific `SKILL.md` files from your agent's instruction surface (`.github/copilot-instructions.md`, `.cursor/rules/`, project-attached files, …).
3. Add `.cache/` to the target repo's `.gitignore`.
4. Inject any required secrets (`JIRA_API_TOKEN`, `GITHUB_TOKEN`, …) via the host platform's secret mechanism.

See [docs/installation.md](docs/installation.md) and [docs/assistants.md](docs/assistants.md) for per-platform details.

### Or — install just the skills via the [Agent Skills](https://skills.sh) ecosystem

```bash
npx skills add wamalalawrence/agent-skills
```

## Skills

The four top-level roles work as one engineering loop, not isolated tools. Each skill explicitly hands off to the others when context, evidence, validation, or scope is missing — see each skill's _Related And Reused Skills_ section for the exact rules.

| Role | Reuses / collaborates with | Purpose |
|---|---|---|
| [`software-engineer`](skills/software-engineer/) | nested [`issue-investigator`](skills/software-engineer/skills/issue-investigator/) + [`code-reviewer`](skills/software-engineer/skills/code-reviewer/); calls `product-owner`, `manual-tester`, `test-automation-engineer` | End-to-end engineering: context discovery, implementation, QA, self-review, PR preparation. |
| [`product-owner`](skills/product-owner/) | calls `software-engineer` (feasibility), `manual-tester` (testability), `test-automation-engineer` (automation-friendly ACs); routes bug-flavored input through `issue-investigator` first | Clarifies goals, requirements, scope, acceptance criteria, UX concerns, handoff notes. |
| [`manual-tester`](skills/manual-tester/) | calls `product-owner`, `software-engineer`, `test-automation-engineer`; uses `issue-investigator` for safe defect reproduction | Plans and executes manual validation, exploratory testing, defect reporting, retest guidance. |
| [`test-automation-engineer`](skills/test-automation-engineer/) | calls `software-engineer` (conventions), `manual-tester` (real scenarios), `product-owner` (ACs); calls `code-reviewer` on its own test code | Designs stable automated tests at the right level and prevents brittle automation. |

Diagram of the actual collaboration graph:

```
              ┌──────────────────┐
              │  product-owner   │
              └─────┬──────┬─────┘
                    │      │
       ┌────────────┘      └────────────┐
       ▼                                 ▼
┌──────────────────┐  pair-programs  ┌──────────────────┐
│ software-engineer│ ◄────────────► │  code-reviewer   │
└─┬──────────┬─────┘                 └────────┬─────────┘
  │          │                                 │
  │Execution modes (`local-workspace` vs `in-repo`)](docs/execution-modes.md)
- [          ▼                                 │
  │   ┌──────────────────┐  evidence/repro    │
  │   │ issue-investigator│ ──────────────────►│
  │   └─────────┬────────┘                    │
  │             │                              │
  ▼             ▼                              ▼
┌──────────────────┐  regression candidates ┌──────────────────────────┐
│  manual-tester   │ ─────────────────────► │ test-automation-engineer │
└──────────────────┘                         └──────────────────────────┘
```

## Documentation

- [Installation & `setup.init`](docs/installation.md)
- [Configuration & multi-project workspaces](docs/configuration.md)
- [Using with your AI assistant](docs/assistants.md)
- [Starter prompts](docs/prompts.md)
- [Roadmap](ROADMAP.md) · [Support](SUPPORT.md) · [Governance](GOVERNANCE.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

## Design Principles

- **Portable:** no company names, hostnames, tokens, repository names, or local paths inside skill files.
- **Context-aware:** skills use issue context, linked docs, repository conventions, tests, and CI signals before recommending changes.
- **Token-conscious:** gather the smallest useful evidence pack first, then expand only when ambiguous or high risk.
- **Collaborative:** implementation, review, and issue resolution are one engineering loop, not isolated activities.
- **Maintainer-realistic:** governance, support, and roadmap promises match a solo-maintainer open-source project.

## Contributing

This is a solo-maintained project I built for my own engineering work and shared as a public good. **Issues and PRs are not actively solicited.** I may not respond, may close work that doesn't fit the project's direction, and reserve the right to keep the scope small.

If you still want to send something, the bar is in [CONTRIBUTING.md](CONTRIBUTING.md): focused, portable, and easy for one person to verify in an evening. Forking is a perfectly fine alternative if your needs diverge.

## License

[MIT](LICENSE).
