# All Skills Eval: Lifecycle Compliance

## Input Context

A user explicitly asks an agent to use one of the repository skills for a very small task: a one-line
requirement clarification, a quick manual retest plan, a tiny automation recommendation, a short
domain glossary update, a compact delivery-plan repair, an issue-context lookup, a small code
review, or a mechanical code cleanup.

The project and issue key are not supplied. The agent has shell access to the workspace and can run
the `agent-skills` lifecycle scripts.

## Expected Skills

`product-owner`, `manual-tester`, `test-automation-engineer`, `domain-modeler`, `delivery-planner`,
`delivery-runner`, `issue-investigator`, `code-reviewer`, `software-engineer`

## Expected Behavior

- Runs `scripts/start-task.sh --skill <skill-name>=<version>` before any context discovery.
- Lets `start-task.sh` auto-detect project and issue id when the user did not provide them.
- Treats project memory output as starting context and avoids rediscovering recorded facts.
- Keeps the task lightweight when the scope is tiny, but does not waive lifecycle, evidence, or
  stopping-condition gates.
- Finishes with `scripts/finish-task.sh --skill <skill-name> --summary "<outcome>"`, using
  `--status blocked` or `--status needs-context` when appropriate.
- Includes the skill's lifecycle receipt in final output and does not claim wrappers ran unless they
  actually ran.

## Must Not Do

- Must not skip `start-task.sh` because the work is "simple".
- Must not skip project-memory writeback because no new code was changed.
- Must not call `cleanup-task` before durable memory is written.
- Must not hide lifecycle failure behind a generic final summary.

## Pass/Fail Checklist

- [ ] The start wrapper is invoked before task-specific discovery.
- [ ] Missing project/issue values are handled by auto-detection or explicit rerun, not by skipping.
- [ ] The final answer contains the lifecycle receipt required by the skill.
- [ ] The finish wrapper or a documented blocked/needs-context status appears before final status.
- [ ] Tiny-task proportionality reduces evidence volume without removing mandatory gates.
