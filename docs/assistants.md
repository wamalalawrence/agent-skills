# Using With Your AI Assistant

Skills are plain Markdown files with YAML frontmatter under [`../skills/`](../skills/), conforming
to the [Agent Skills specification](https://agentskills.io/specification). How they are loaded
depends on the assistant **and on the execution mode** ([execution-modes.md](execution-modes.md)).
The `setup.init` command creates `<workspace-root>/.skills` so any assistant that looks at
workspace-level skill folders will find them in `local-workspace` mode; in `in-repo` mode the skills
must be vendored or referenced from inside the target repo.

## Local assistants (`local-workspace` mode)

| Assistant                                                 | How it loads these skills                                                                                                                                                                                                                                     |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anthropic Claude (skills-aware clients, e.g. Claude Code) | Point the client at `<workspace-root>/.skills` or `agent-skills/skills`. Each `SKILL.md` declares its own `name` and `description` in YAML frontmatter for skill discovery.                                                                                   |
| Cursor / Windsurf / Continue (local)                      | Reference the relevant `SKILL.md` from your project rules or attach it as instructions for the chat.                                                                                                                                                          |
| GitHub Copilot Chat (VS Code/JetBrains)                   | Copilot does not have a native "skill source" picker. Attach a `SKILL.md` to a chat with `#file:`, copy its contents into `.github/copilot-instructions.md`, or save it as a [prompt file](https://code.visualstudio.com/docs/copilot/copilot-customization). |
| ChatGPT / generic chat                                    | Paste the relevant `SKILL.md` into the conversation, or upload the `skills/<role>/` folder, before asking it to perform the workflow.                                                                                                                         |

## Online / cloud agents (`in-repo` mode)

These agents run inside a single target repository and cannot reach a sibling `agent-skills`
checkout. The pattern is the same for all of them:

1. Commit `.agent-skills.yml` at the repo root (see
   [`.agent-skills.example.yml`](../.agent-skills.example.yml)).
2. Vendor the `skills/` folder you actually use (e.g. as `.agent-skills/skills/` via
   `git submodule add` of this repo, or by copying the role you need).
3. Reference it from the agent's instruction surface for that platform.
4. Add `.cache/` to the repo's `.gitignore`.
5. Inject any required secrets (`JIRA_API_TOKEN`, `GITHUB_TOKEN`, …) via the platform's secret
   mechanism.

| Agent                                       | How it loads these skills                                                                                                                                                                                                                                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GitHub Copilot coding agent (github.com)    | Reference the relevant vendored `SKILL.md` from `.github/copilot-instructions.md` so it is loaded for every coding-agent task; alternatively attach specific `SKILL.md` files in the issue/PR description that triggers the agent. Repository / org Actions secrets become the env vars the skills need. |
| Cursor cloud / background agents            | Reference vendored `SKILL.md` files from `.cursor/rules/*.mdc` or attach them in the agent's task prompt. Use Cursor's secret store for credentials.                                                                                                                                                     |
| Devin / Codex / Codegen-style agents        | Add the vendored `SKILL.md` to the project knowledge / repo-onboarding instructions so the agent loads it before each session.                                                                                                                                                                           |
| GitHub Codespaces / Gitpod                  | The repo is the workspace; commit `.agent-skills.yml` and treat the Codespace as `in-repo` mode. Codespaces user/repo secrets become the env vars.                                                                                                                                                       |
| Claude.ai web (project with files attached) | Attach the relevant `SKILL.md` and `.agent-skills.yml` to the project so they are loaded into every conversation in that project.                                                                                                                                                                        |

When in doubt, open the `SKILL.md` for the role you want and tell your assistant "follow this
workflow for the next task". The skills are written to be self-contained and will detect the
execution mode during their **Setup Preflight** phase.
