# agent-skills

Reusable [Agent Skills](https://agentskills.io/) for software-engineering work — portable,
role-shaped workflows your AI assistant can load on demand so the same model produces
senior-engineer, product-owner, tester, or reviewer output instead of generic answers.

> **Status:** `0.17.0` — pre-1.0. Core skill set is shipped and stable enough for public use;
> interfaces may still evolve.

New here? Start with the [quickstart](docs/quickstart.md), then read [starter
prompts](docs/starter-prompts.md), [examples](docs/examples/README.md), the
[requirement-understanding workflow](docs/requirement-understanding.md) every skill runs before
acting, [validation](docs/validation.md), [known limitations](docs/known-limitations.md), and the
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

### [`software-engineer`][software-engineer] (top-level)

- Key collaborators: `product-owner`, `manual-tester`, `test-automation-engineer`.
- Purpose: end-to-end engineering — context discovery, implementation, QA, self-review,
  PR preparation.

### [`product-owner`][product-owner] (top-level)

- Key collaborators: `software-engineer`, `manual-tester`, `test-automation-engineer`.
- Purpose: clarifies goals, requirements, scope, acceptance criteria, UX concerns,
  and handoff notes.

### [`manual-tester`][manual-tester] (top-level)

- Key collaborators: `product-owner`, `software-engineer`, `test-automation-engineer`.
- Purpose: plans and executes manual validation, exploratory testing, defect
  reporting, and retest guidance.

### [`test-automation-engineer`][tae] (top-level)

- Key collaborators: `software-engineer`, `manual-tester`, `product-owner`.
- Purpose: designs stable automated tests at the right level and prevents brittle
  automation.

### [`issue-investigator`][issue-investigator] (nested support)

- Key collaborators: `software-engineer`, `manual-tester`, `product-owner`.
- Purpose: builds issue evidence, reproduction steps, root-cause status, and
  handoff.

### [`code-reviewer`][code-reviewer] (nested support)

- Key collaborators: `software-engineer`, `test-automation-engineer`,
  `issue-investigator`.
- Purpose: reviews diffs against issue context, evidence packs, quality risks, and
  definition of done.

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
- [Requirement-understanding workflow](docs/requirement-understanding.md) — the gate every
  relevant skill runs before implementation, review, testing, or automation
- [Requirement-understanding scorecard](docs/requirement-understanding-scorecard.md)
- [Skill performance review](docs/skill-performance-review.md)
- [Eval runs](eval-runs/README.md)
- [Release checklist](docs/release-checklist.md)
- [Skill boundaries](docs/skill-boundaries.md)
- [Severity and confidence definitions](docs/severity-and-confidence.md)
- [Known limitations](docs/known-limitations.md)
- [Versioning policy](docs/versioning.md)
- [Destructive-action safety policy](docs/destructive-action-safety.md) — what every skill
  must refuse to do, and why
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
