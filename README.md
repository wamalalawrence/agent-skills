# agent-skills

Reusable [Agent Skills](https://agentskills.io/) for software-engineering work — portable, role-shaped workflows your AI assistant can load on demand so the same model produces senior-engineer, product-owner, tester, or reviewer output instead of generic answers.

> **Status:** `0.3.0` — pre-1.0. Core skill set is shipped and stable enough for public use; interfaces may still evolve.

## Why Skills

A general-purpose LLM is a general practitioner: capable, broad, but not specialized. A skill turns that same model into a specialist for a narrow, high-value task — with the right context, the right checklist, and the right stopping conditions.

- **Without a skill:** you ask "fix this bug" and hope the model remembers your standards.
- **With a skill:** the model follows a tested workflow — gather just enough evidence, propose a safe plan, implement, self-review, and stop when context is missing instead of guessing.

## Install

Two options.

**Recommended — one-command setup that wires up your workspace:**

```bash
git clone https://github.com/wamalalawrence/agent-skills.git
cd agent-skills
./setup.init
```

**Or — install just the skills via the [Agent Skills](https://skills.sh) ecosystem:**

```bash
npx skills add wamalalawrence/agent-skills
```

See [docs/installation.md](docs/installation.md) for the recommended workspace layout, all flags, manual setup, and what `setup.init` does.

## Skills

| Role | Nested skills | Purpose |
|---|---|---|
| [`software-engineer`](skills/software-engineer/) | [`issue-investigator`](skills/software-engineer/skills/issue-investigator/), [`code-reviewer`](skills/software-engineer/skills/code-reviewer/) | End-to-end engineering: context discovery, implementation, QA, self-review, PR preparation. |
| [`product-owner`](skills/product-owner/) | — | Clarifies goals, requirements, scope, acceptance criteria, UX concerns, handoff notes. |
| [`manual-tester`](skills/manual-tester/) | — | Plans and executes manual validation, exploratory testing, defect reporting, retest guidance. |
| [`test-automation-engineer`](skills/test-automation-engineer/) | — | Designs stable automated tests at the right level and prevents brittle automation. |

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

Contributions that improve portability, clarity, safety, or real-world usefulness are welcome — start with [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
