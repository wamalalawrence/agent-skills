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

Install once on the machine:

```bash
npx @wamalalawrence/agent-skills install
```

Then open any repository and describe the work. The skills are already discoverable to the agent in
your editor, so there is nothing to attach and nothing to configure:

```text
Use Wamala to investigate why page 2 of invoice search loses the status filter.
```

If you already know the owner, invoke it directly. That is faster and always supported:

```text
Use the software-engineer skill for this repository. Inspect the issue and the codebase, identify
the smallest safe implementation plan, ask if required context is missing, then implement and
validate the change.
```

Setup asks for no credentials and needs no list of your projects. When a task actually needs an
external service, access is resolved on demand — see [access resolution](access-resolution.md).

Useful once installed:

```bash
agent-skills verify     # is the installation healthy, and which hosts see the skills
agent-skills doctor     # what can this environment actually do right now
agent-skills project    # what was inferred about the repository you are in
```

## Zero-config repositories are normal

A repository with no `.env`, no `.skills`, no sibling `agent-skills` clone, and no
`.agent-skills.yml` is a supported case, not a degraded one. Project context is derived from the
repository itself: git root, remote, base branch, stack, build system, package manager, commands,
and CI.

```bash
cd ~/code/some-new-project
agent-skills project
```

Anything that could not be established safely is listed under `confirm before relying on` rather
than asserted, so the agent knows which facts to establish before they matter.

Add a committed [`.agent-skills.yml`](../.agent-skills.example.yml) only when inference is not good
enough — an unusual build command, a non-conventional base branch, a coverage target. It contains no
secrets, ever. See [configuration](configuration.md).

## Cloud and remote agents

A cloud agent runs on a machine that cannot see your home directory, so the global install does not
reach it. Use the in-repo mechanism instead:

1. Copy [`.agent-skills.example.yml`](../.agent-skills.example.yml) to `.agent-skills.yml` in the
  target repository and fill in the `project:` block.
2. Vendor the skills you need into the repository, or reference the relevant `SKILL.md` files from
  the agent's instruction surface.
3. Put secrets in the host platform's secret mechanism, not in `.agent-skills.yml`.
4. Add `.cache/` to the repository's `.gitignore`.

See [execution modes](execution-modes.md) for the full comparison.

## Upgrading from v0.36.x

Your existing workspace keeps working. To move:

```bash
agent-skills update
agent-skills migrate
```

Nothing is deleted and no secret is copied without an explicit request. Details in
[installation](installation.md#upgrading-from-v036x-workspace-installation).

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

## External access at a glance

Nothing is requested at install time. When a task needs an external service, one generic mechanism
resolves it:

```bash
agent-skills access resolve --service jira --require host,login,token --secret token
```

The order is fixed and documented: an already-authenticated tool or session first (a logged-in
`gh`, an MCP server the host already has), then the process environment, then project-local
configuration including a legacy `.env`, then a named user-level identity, and only then lazy setup.

Credentials belong to accounts, not projects, so two repositories can share one work account
without re-entering a token. Secrets go to the OS credential store, never to a repository and never
into the conversation. Full contract: [access resolution](access-resolution.md).

## What not to expect

- These skills are not deterministic software.
- They do not replace human review.
- They do not provide tracker, GitHub, linked document store, CI, or production access by themselves.
- They do not include private company standards; supply those from your repository or prompt.
- They do not come with an SLA, warranty, or guarantee of correctness.

## Understanding before action

Every relevant skill runs the
[requirement-understanding workflow](requirement-understanding.md) before implementing, reviewing,
testing, or automating. The gate writes a short `Requirement Understanding` block (twelve fields)
at the top of the output and applies three binding rules:

- `unknown` / `low` confidence — the agent must not implement, must not produce tracker-ready
  output, must not assert pass/fail tests, and must not give a bare `PASS` review. It asks for
  clarification or evidence instead.
- `medium` confidence — the agent may plan, draft, or run read-only checks, but every
  load-bearing assumption stays visible.
- `high` confidence — the agent may proceed within the understood scope.

If you ask the agent to skip this step ("just write the code", "just ship it"), the gate is
intentionally not waivable by user prompt. See
[requirement-understanding examples](examples/requirement-understanding.md) and the
[requirement-understanding scorecard](requirement-understanding-scorecard.md).

Next, review the [examples](examples/README.md), [skill boundaries](skill-boundaries.md), and
[severity/confidence definitions](severity-and-confidence.md) to see the expected output contracts
in practice.
