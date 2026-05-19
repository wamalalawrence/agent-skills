# code-reviewer

Issue-aware code review workflow for working diffs, branches, commits, and pull requests.

See [SKILL.md](./SKILL.md) for the full workflow.

## How it is used

| Mode       | Trigger                                  | Diff scope                      | Severity filter                          |
| ---------- | ---------------------------------------- | ------------------------------- | ---------------------------------------- |
| Inner loop | Auto: end of `software-engineer` Phase 2 | `git diff --staged`             | `${CODE_REVIEWER_INNER_LOOP_SEVERITIES}` |
| Outer loop | Auto: end of `software-engineer` Phase 3 | `git diff origin/<base>...HEAD` | `${CODE_REVIEWER_SHOW_SEVERITIES}`       |
| PR         | Manual or PR review                      | Pull request diff               | `${CODE_REVIEWER_SHOW_SEVERITIES}`       |
| Manual     | User-supplied diff or excerpt            | Provided content                | Requested severities                     |

## Review layers

1. Issue alignment: checks the diff against tracker tickets (Jira, GitHub Issues, GitLab Issues, etc.), support tickets, bug reports,
  feature requests, task descriptions, acceptance criteria, and linked context.
2. Engineering quality: checks correctness, maintainability, tests, security, performance,
  observability, compatibility, and regression risk.

## Collaborates with

- [`issue-investigator`](../issue-investigator/) when ticket context, root cause, or expected
  behavior is unclear.
- [`software-engineer`](../../) for implementation quality, architecture, testability, and
  production-risk judgment.

## Required environment

Run [`../../../../setup.init`](../../../../setup.init) from the `agent-skills` folder for the
simplest setup path. See [SKILL.md](./SKILL.md#required-environment) for details. Minimum for
repository-aware review: `WORKSPACE_ROOT`, `PROJECTS_JSON`, and `GITHUB_DEFAULT_BRANCH`.
Model routing is owned by the host (Copilot Chat, Claude Code, Cursor, etc.); the skill
intentionally does not expose its own model knob — the previous `CODE_REVIEWER_MODEL`
variable was removed in v0.20.0.
