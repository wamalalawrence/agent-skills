# agent-skills

`agent-skills` is an open-source collection of reusable AI agent skills for public-good software engineering work. The goal is practical: give teams and individual maintainers portable, well-documented workflows for context-aware implementation, review, issue resolution, and delivery.

The project is intentionally small today. Its core skill set covers product definition, engineering delivery, manual validation, and test automation. Future skills should grow from real use, not from a speculative taxonomy.

## Why Skills

A general-purpose LLM is a general practitioner: capable, broad, but not specialized. A skill turns that same model into a specialist for a narrow, high-value task — with the right context, the right checklist, and the right stopping conditions.

Without a skill, you ask "fix this bug" and hope the model remembers your standards.
With a skill, the model follows a tested workflow: gather just enough evidence, propose a safe plan, implement, self-review, and stop when context is missing instead of guessing.

`agent-skills` is the specialist toolkit: a small set of role-shaped workflows your AI assistant can load on demand, so the same model produces senior-engineer, product-owner, tester, or reviewer output instead of generic answers.

## Project Status

Current version: `0.2.0`

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
├── setup.init
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

Tested on macOS and Linux with `bash` and `zsh`. Windows users should run via WSL or Git Bash.

### 1. Put `agent-skills` next to your repos

`agent-skills` is designed to live alongside the projects it reasons about, not inside one of them and not at the root of your home directory. The recommended layout:

```text
~/work/                       # any folder you control; this is the "workspace root"
├── agent-skills/             # this repository
├── repo-a/
├── repo-b/
└── .env                      # generated by setup.init, gitignored
```

`setup.init` will refuse to write into `$HOME`, `/`, or system directories so it cannot accidentally pollute your shell environment. If you cloned `agent-skills` directly into `$HOME`, move it under a real workspace folder first, or pass `--workspace-root /path/to/work`.

### 2. Run the setup command

```bash
cd agent-skills
./setup.init
```

The command asks a short set of questions, then creates or updates:

- `.env` in the workspace root (a clearly marked generated block; manual edits **outside** that block are preserved on rerun, edits **inside** are overwritten).
- `.jira-config.yml` in the workspace root, only if you opt in to Jira setup.
- `.skills` in the workspace root as a symlink to `agent-skills/skills`.

For non-interactive bootstrap or CI checks:

```bash
./setup.init --yes --no-jira --workspace-root /path/to/work
```

To re-check an existing setup at any time:

```bash
./setup.init --verify
```

Manual setup is still supported when you want full control:

```bash
cp agent-skills/.env.example /path/to/work/.env
$EDITOR /path/to/work/.env

# Optional: Jira CLI config, only if you use the jira CLI directly.
cp agent-skills/.jira-config.example.yml /path/to/work/.jira-config.yml
$EDITOR /path/to/work/.jira-config.yml
```

### 3. Tell your AI assistant where the skills live

These are plain Markdown files with YAML frontmatter under [`./skills/`](./skills/). How they are loaded depends on the assistant. The `setup.init` command creates `<workspace-root>/.skills` so any assistant that looks at workspace-level skill folders will find them, but you may also need to wire them up explicitly:

| Assistant | How it loads these skills |
|---|---|
| Anthropic Claude (skills-aware clients, e.g. Claude Code) | Point the client at `<workspace-root>/.skills` or `agent-skills/skills`. Each `SKILL.md` declares its own `name` and `description` in YAML frontmatter for skill discovery. |
| Cursor / Windsurf / Continue | Reference the relevant `SKILL.md` from your project rules or attach it as instructions for the chat. |
| GitHub Copilot Chat (VS Code/JetBrains) | Copilot does not have a native "skill source" picker. Attach a `SKILL.md` to a chat with `#file:`, copy its contents into `.github/copilot-instructions.md`, or save it as a [prompt file](https://code.visualstudio.com/docs/copilot/copilot-customization). |
| ChatGPT / generic chat | Paste the relevant `SKILL.md` into the conversation, or upload the `skills/<role>/` folder, before asking it to perform the workflow. |

When in doubt, open the `SKILL.md` for the role you want and tell your assistant "follow this workflow for the next task". The skills are written to be self-contained.

## Try A First Prompt

After setup, start with one of these prompts. Replace the bracketed parts with your own repo, issue, or goal.

```text
Use the software-engineer skill to inspect [repo/path] and propose a safe implementation plan for: [short issue or feature description].
```

```text
Use the issue-investigator skill to investigate [Jira key, GitHub issue URL, or bug report] and tell me the expected behavior, actual behavior, evidence, root cause confidence, and recommended next action.
```

```text
Use the code-reviewer skill in outer mode to review my current branch against [base branch] and [issue key or acceptance criteria].
```

```text
Use the product-owner skill to turn this rough idea into a delivery-ready story with scope, assumptions, open questions, and acceptance criteria: [idea].
```

```text
Use the manual-tester skill to create a lean manual test plan for [story, feature, or bug fix] using these acceptance criteria: [criteria].
```

```text
Use the test-automation-engineer skill to decide what should be automated for [workflow or regression risk], what should remain manual, and which test level is best.
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

The setup command and copied template are intentionally safe: they can describe the current workspace as a single local project, leave external systems blank, and avoid fake credentials. That is enough for generic planning or a first local dry run, but not enough for issue-aware or repository-changing work unless the generated values match the real workspace.

When loading `.env` manually in a shell, export the values so child commands can see them:

```bash
set -a
source .env
set +a
```

If `.env` is missing, a required value is blank, a copied bootstrap value would make the project identity ambiguous, or a Jira ticket cannot be read, the skill warns and stops before doing accuracy-sensitive work. Silent fallbacks are treated as a bug because they produce wrong work.

`.jira-config.yml` is optional. Jira-driven work can use the environment variables in `.env` directly, but if neither Jira credentials nor a user-supplied ticket summary are available, the issue-aware skills stop and ask for context.

## What setup.init Automates

`setup.init` keeps onboarding small while preserving the accuracy guardrails that make the skills useful.

- Refuses to use `$HOME`, `/`, or system directories as the workspace root, so a fresh clone in the wrong place cannot pollute your environment.
- Defaults the workspace root to the parent of `agent-skills`, but always lets you override it with `--workspace-root`.
- Creates `.env` from [`.env.example`](./.env.example) when missing.
- Adds or refreshes a marked generated block (`# >>> agent-skills setup.init` ... `# <<< agent-skills setup.init`) for `WORKSPACE_ROOT`, `ORG_NAME`, `GITHUB_ORG`, `GITHUB_DEFAULT_BRANCH`, and `PROJECTS_JSON`. Edits inside the markers are overwritten on rerun; edits outside are preserved verbatim.
- Detects sibling git repositories and writes a starter `PROJECTS_JSON` map. Build and format commands are inferred from `pom.xml` / `build.gradle` / `package.json` (including `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`) / `pyproject.toml` (Poetry-aware) / `go.mod`.
- Detects the GitHub owner from sibling repo `remote.origin.url` first, then falls back to `gh api user --jq .login`, then leaves it blank.
- Optionally creates `.jira-config.yml` from [`.jira-config.example.yml`](./.jira-config.example.yml) and seeds the default project key.
- Creates a `.skills` symlink in the workspace root for assistants that can read skills from a workspace folder.
- Adds an idempotent agent-skills block to `<workspace-root>/.gitignore` covering `.env`, `.env.local`, `.env.*.local`, `.jira-config.yml`, `.skills`, and `.cache/`, so a workspace that is itself a git repo does not show those files as uncommitted changes (and `.env` does not risk leaking secrets). The block is created only when a `.gitignore` already exists or the workspace root is a git repo.
- Validates that `.env` parses by trying `python3` first, then `ruby`. JSON validation is only skipped when neither interpreter is installed.
- Supports `./setup.init --verify` to re-check an existing setup without writing anything: required env vars, `PROJECTS_JSON` shape, that every project path exists, and that the `.skills` symlink target resolves.

After setup, review `.env` once before serious code work. The command can detect obvious defaults, but it cannot know every repository's exact build, format, runtime, deployment, or Jira conventions.

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
