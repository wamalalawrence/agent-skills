# issue-investigator

Issue investigation workflow for Jira tickets, GitHub issues, support tickets, incidents, regressions, feature requests, and technical tasks.

See [SKILL.md](./SKILL.md) for the full workflow.

## What it does

- Reads full issue context: title, description, comments, attachments, acceptance criteria, linked docs, logs, screenshots, and related tickets.
- Classifies the issue type and separates expected behavior, actual behavior, facts, assumptions, and unknowns.
- Investigates code, configuration, data, CI, deployments, environments, and reproduction evidence where available.
- Produces a practical next-action recommendation before implementation begins.

## Collaborates with

- [`software-engineer`](../../) for technical code analysis, implementation feasibility, and validation planning.
- [`code-reviewer`](../code-reviewer/) after a fix or implementation exists.
- [`product-owner`](../../../product-owner/) when intended behavior or acceptance criteria are unclear.

## Required environment

Run [`../../../../setup.init`](../../../../setup.init) from the `agent-skills` folder for the simplest setup path. See [SKILL.md](./SKILL.md#required-environment) for details. Jira and Confluence variables are required only when those systems are the source of issue context.