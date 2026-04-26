# Quickstart

`agent-skills` is a collection of reusable AI agent skill definitions for software delivery work.
The files are Markdown instructions with YAML frontmatter. They are meant to help an AI assistant
act more like a specific collaborator: engineer, product owner, manual tester, or test automation
engineer.

Use this repo when you want portable, evidence-first workflows for:

- implementing code changes
- refining requirements and acceptance criteria
- planning or reporting manual tests
- designing stable automated tests
- investigating issues before guessing at a fix
- reviewing code against the actual task and evidence

## Fastest path

1. Open the `SKILL.md` for the role you need.
2. Attach or paste it into your assistant.
3. Ask the assistant to follow that workflow for one task.
4. Provide the repository, issue, acceptance criteria, logs, or test evidence the workflow asks for.

Example:

```text
Use the software-engineer skill from skills/software-engineer/SKILL.md.
Work on this repository. First gather the smallest useful context, then propose a short plan before
changing files.
```

## Local-workspace mode

Use local-workspace mode when the agent runs on your laptop and can see several sibling
repositories.

```bash
git clone https://github.com/wamalalawrence/agent-skills.git
cd agent-skills
./setup.init
```

This creates workspace-level configuration and a `.skills` link that local assistants can reference.
See [installation](installation.md) and [configuration](configuration.md) for details.

## In-repo / cloud-agent mode

Use in-repo mode when the agent runs inside one repository, such as GitHub Copilot coding agent,
Cursor cloud/background agents, Codex, Codespaces, Gitpod, Devin, or a web chat with the repository
attached.

1. Copy [`.agent-skills.example.yml`](../.agent-skills.example.yml) to `.agent-skills.yml` in the
  target repository.
2. Fill in the `project:` block.
3. Vendor the skills you need into the repository, or reference the relevant `SKILL.md` files from
  the agent's instruction surface.
4. Put secrets in the host platform's secret mechanism, not in `.agent-skills.yml`.
5. Add `.cache/` to the target repository's `.gitignore`.

See [execution modes](execution-modes.md) for the full mode comparison.

## Starter prompts

Use one of these as a first practical prompt. For copy-paste prompts covering all skills and
multi-skill workflows, see [starter prompts](starter-prompts.md).

### `software-engineer`

```text
Use the software-engineer skill for this repository. Inspect the issue and the codebase, identify
the smallest safe implementation plan, ask if required context is missing, then implement and
validate the change.
```

### `product-owner`

```text
Use the product-owner skill to turn this rough request into implementation-ready scope. Produce
clear acceptance criteria, edge cases, out-of-scope items, and open questions.
```

### `manual-tester`

```text
Use the manual-tester skill to create a focused validation plan for this change. Include setup,
test charters, expected results, regression areas, and defect-reporting guidance.
```

### `test-automation-engineer`

```text
Use the test-automation-engineer skill to decide what should be automated for this change. Choose
the right test level, avoid brittle checks, and describe the validation command.
```

## What not to expect

- These skills are not deterministic software.
- They do not replace human review.
- They do not provide Jira, GitHub, Confluence, CI, or production access by themselves.
- They do not include private company standards; supply those from your repository or prompt.
- They do not come with an SLA, warranty, or guarantee of correctness.

Next, review the [examples](examples/README.md), [skill boundaries](skill-boundaries.md), and
[severity/confidence definitions](severity-and-confidence.md) to see the expected output contracts
in practice.
