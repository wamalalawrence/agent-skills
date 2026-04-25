# Using With Your AI Assistant

Skills are plain Markdown files with YAML frontmatter under [`../skills/`](../skills/), conforming to the [Agent Skills specification](https://agentskills.io/specification). How they are loaded depends on the assistant. The `setup.init` command creates `<workspace-root>/.skills` so any assistant that looks at workspace-level skill folders will find them, but you may also need to wire them up explicitly.

| Assistant | How it loads these skills |
|---|---|
| Anthropic Claude (skills-aware clients, e.g. Claude Code) | Point the client at `<workspace-root>/.skills` or `agent-skills/skills`. Each `SKILL.md` declares its own `name` and `description` in YAML frontmatter for skill discovery. |
| Cursor / Windsurf / Continue | Reference the relevant `SKILL.md` from your project rules or attach it as instructions for the chat. |
| GitHub Copilot Chat (VS Code/JetBrains) | Copilot does not have a native "skill source" picker. Attach a `SKILL.md` to a chat with `#file:`, copy its contents into `.github/copilot-instructions.md`, or save it as a [prompt file](https://code.visualstudio.com/docs/copilot/copilot-customization). |
| ChatGPT / generic chat | Paste the relevant `SKILL.md` into the conversation, or upload the `skills/<role>/` folder, before asking it to perform the workflow. |

When in doubt, open the `SKILL.md` for the role you want and tell your assistant "follow this workflow for the next task". The skills are written to be self-contained.
