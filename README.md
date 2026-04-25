# agent-skills

`agent-skills` is an open-source collection of reusable AI agent skills for public-good software engineering work. The goal is practical: give teams and individual maintainers portable, well-documented workflows for context-aware implementation, review, issue resolution, and delivery.

The project is intentionally small today. Its core skill set covers product definition, engineering delivery, manual validation, and test automation. Future skills should grow from real use, not from a speculative taxonomy.

## Project Status

Current version: `0.1.0`

This repository is pre-1.0. The structure is stable enough for public use, but skill interfaces, recommended environment variables, and documentation conventions may still change as the project learns from real contributors and users.

## Design Principles

- Portable: no company names, hostnames, tokens, repository names, or local paths inside skill files.
- Context-aware: skills use issue context, linked docs, repository conventions, tests, and CI signals before recommending or making changes.
- Token-conscious: skills gather the smallest useful evidence pack first, then expand only when the work is ambiguous or high risk.
- Collaborative: implementation, review, and issue resolution are part of one engineering loop, not isolated activities.
- Maintainer-realistic: governance, support, and roadmap promises match a solo-maintainer open-source project.

## Skills

Skills are organized by role. A top-level role owns the main workflow; nested sub-skills specialize that role without becoming separate public entry points too early.

| Role | Status | Nested skills | Purpose |
|---|---|---|---|
| [`software-engineer`](./skills/software-engineer/) | Shipped, flagship | [`issue-investigator`](./skills/software-engineer/skills/issue-investigator/), [`code-reviewer`](./skills/software-engineer/skills/code-reviewer/) | End-to-end engineering: context discovery, implementation, QA, self-review, and PR preparation. Includes issue investigation plus inner-loop and outer-loop code review. |
| [`product-owner`](./skills/product-owner/) | Shipped, core | none | Clarifies product goals, requirements, scope, acceptance criteria, UX concerns, and handoff notes. |
| [`manual-tester`](./skills/manual-tester/) | Shipped, core | none | Plans and executes manual validation, exploratory testing, defect reporting, evidence collection, and retest guidance. |
| [`test-automation-engineer`](./skills/test-automation-engineer/) | Shipped, core | none | Designs stable automated tests at the right level, integrates them into CI, and prevents brittle or low-value automation. |

These four skills are the current public core. Possible future roles include `software-architect` and `release-manager`, but only when real usage justifies them.

## How The Core Skills Work Together

- [`product-owner`](./skills/product-owner/) defines what should be built, why it matters, and how success should be recognized.
- [`software-engineer`](./skills/software-engineer/) implements, reviews, and validates the technical delivery path.
- [`manual-tester`](./skills/manual-tester/) validates real behavior, explores workflows, and reports defects with evidence.
- [`test-automation-engineer`](./skills/test-automation-engineer/) turns stable, high-value checks into maintainable automated tests.

Each skill is useful on its own, but the handoffs are explicit so the same repository can support a full software delivery workflow without duplicating guidance across skills.

## Repository Layout

```text
agent-skills/
├── README.md
├── CONTRIBUTING.md
├── GOVERNANCE.md
├── ROADMAP.md
├── SUPPORT.md
├── SECURITY.md
├── CHANGELOG.md
├── VERSION
├── LICENSE
├── .env.example
├── .jira-config.example.yml
└── skills/
    ├── product-owner/
    │   ├── SKILL.md
    │   └── README.md
    ├── software-engineer/
    │   ├── SKILL.md              # parent engineering role workflow
    │   ├── README.md
    │   ├── references/           # long-form engineering checklists
    │   │   ├── architecture-patterns.md
    │   │   ├── code-review-checklist.md
    │   │   ├── security-checklist.md
    │   │   └── sonarqube-checklist.md
    │   └── skills/               # nested engineering specializations
    │       ├── code-reviewer/
    │       │   ├── SKILL.md
    │       │   └── README.md
    │       └── issue-investigator/
    │           ├── SKILL.md
    │           └── README.md
    ├── manual-tester/
    │   ├── SKILL.md
    │   └── README.md
    └── test-automation-engineer/
        ├── SKILL.md
        └── README.md
```

## Quick Start

```bash
# 1. Place this repository at the root of a workspace.
#    /workspace
#      ├── agent-skills/
#      ├── repo-a/
#      ├── repo-b/
#      └── .env                   # workspace-level real env, gitignored

# 2. Create your real workspace environment from the template.
#    The copied defaults support a local bootstrap run. Customize them before
#    relying on issue-aware, code-changing, PR, or release work.
cp agent-skills/.env.example .env
$EDITOR .env

# 3. Optional: Jira CLI config, only if you use the jira CLI directly.
cp agent-skills/.jira-config.example.yml .jira-config.yml
$EDITOR .jira-config.yml

# 4. Tell your AI assistant where to find the skills.
#    For VS Code Copilot, attach the folder as a skill source, or symlink:
ln -s agent-skills/skills .skills
```

## Configuration Model

```text
.env in the workspace root
   |
   |-- loaded into the shell or agent environment
   |
   `-- referenced inside SKILL.md as ${VAR_NAME}
     skills never contain literal hostnames, tokens, repo names, or org names
```

The copied template is intentionally safe: it can describe the current workspace as a single local project, leaves external systems blank, and avoids fake credentials. That is enough for generic planning or a first local dry run, but not enough for issue-aware or repository-changing work unless the defaults match the real workspace.

If `.env` is missing, a required value is blank, a copied bootstrap value would make the project identity ambiguous, or a Jira ticket cannot be read, the skill warns and stops before doing accuracy-sensitive work. Silent fallbacks are treated as a bug because they produce wrong work.

`.jira-config.yml` is optional. Jira-driven work can use the environment variables in `.env` directly, but if neither Jira credentials nor a user-supplied ticket summary are available, the issue-aware skills stop and ask for context.

## Multi-Project Workspaces

Declare repositories once via `PROJECTS_JSON` in `.env`. Skills use this to identify the current project, stack, runtime, base branch, build command, and formatting command.

```jsonc
PROJECTS_JSON='[
  {"name":"example-api",    "path":"example-api",    "stack":"java",       "base_branch":"main", "build":"mvn clean verify",   "format":"mvn fmt:format && mvn fmt:check"},
  {"name":"example-web",    "path":"example-web",    "stack":"typescript", "base_branch":"main", "build":"npm ci && npm test", "format":"npm run lint && npm run format:check"},
  {"name":"example-worker", "path":"example-worker", "stack":"python",     "base_branch":"main", "build":"pytest",             "format":"ruff check . && ruff format --check ."}
]'
```

Per-project keys:

- `name`: short identifier
- `path`: relative path under `${WORKSPACE_ROOT}`
- `stack`: `java`, `typescript`, `python`, `go`, `mixed`, or `other`
- `base_branch`: overrides `${GITHUB_DEFAULT_BRANCH}` for this project
- `build`: full build-and-test command
- `format`: formatter command to run before commit or PR
- optional: `runtime_version`, `coverage_target`, `notes`

## Required Variables

See [`.env.example`](./.env.example) for the full annotated list. The minimum useful setup is:

| Variable | Why |
|---|---|
| `ORG_NAME` | Used in summaries and stakeholder-ready output |
| `WORKSPACE_ROOT` | Anchor for resolving repos, cache, and configs |
| `GITHUB_ORG` | Required only for GitHub repository discovery, clone, push, or PR work |
| `GITHUB_DEFAULT_BRANCH` | Default base branch when a project has no override |
| `PROJECTS_JSON` | Multi-project map with stack and command metadata |
| `CODE_REVIEWER_MODEL` | Optional model-routing hint for the nested `code-reviewer` skill |
| `JIRA_HOST` and `JIRA_API_TOKEN` | Required only for Jira-driven or story-aware modes |

## Versioning And Releases

The project uses semantic versioning in spirit:

- `0.x`: skill contracts and docs may evolve as the public project matures.
- `1.x`: stable skill layout and environment variable expectations.
- Patch releases: documentation fixes, checklist improvements, and compatible clarifications.

Release notes live in [CHANGELOG.md](./CHANGELOG.md). The current version is also recorded in [VERSION](./VERSION).

Repository maintenance uses `main`, short-lived feature branches, pull requests, and version tags. There is no `develop` branch or GitFlow requirement.

## Roadmap, Support, And Governance

- [ROADMAP.md](./ROADMAP.md) explains what is planned and what is intentionally out of scope for now.
- [SUPPORT.md](./SUPPORT.md) explains support expectations, maintenance capacity, and GitHub Sponsors support.
- [GOVERNANCE.md](./GOVERNANCE.md) documents the solo-maintainer governance model.
- [SECURITY.md](./SECURITY.md) explains how to report security concerns.

## Contributing

Contributions are welcome when they improve portability, clarity, safety, or real-world usefulness. Start with [CONTRIBUTING.md](./CONTRIBUTING.md), especially the rules on environment variables, missing context, and skill composition.

## Funding

This is a public-benefit project maintained by one person. GitHub Sponsors support helps fund maintenance time, documentation, triage, and continued development. Sponsorship is appreciated but never required to use the skills.

## License

[MIT](./LICENSE).
