# Documentation

Start here when reading the repository outside GitHub's main README.

- [Quickstart](quickstart.md) - first practical path through setup and skill use.
- [Installation](installation.md) - local-workspace and in-repo setup.
- [Configuration](configuration.md) - environment and project metadata.
- [Execution modes](execution-modes.md) - how skills choose local-workspace vs in-repo mode.
- [Issue tracker / Document store auth discovery](auth-discovery.md) - the order skills must walk before
  declaring auth unavailable, how `${VAR}` placeholders are resolved, the auth preflight
  script, and the troubleshooting table for common failures.
- [Skill-source resolution](skill-source-resolution.md) - which directory the agent must
  treat as the canonical skill source when more than one is present on disk, and how the
  workspace lock file is consulted.
- [Updates](updates.md) - how a user notices a new release and applies it without losing
  local config (`./setup.init --check-updates`, `./setup.init --update`, `git pull`).
- [Lifecycle preflight](lifecycle-preflight.md) - the full contract behind the two commands
  every skill runs (`start-task.sh` / `finish-task.sh`): fallbacks, statuses, durable-fact
  flags, the capability report, and why task size never waives them.
- [Repo knowledge](repo-knowledge.md) - the committed, PR-reviewed tier that lives inside the
  repository being worked on: confidence-scored lessons, budgeted and ranked recall, the
  promotion path up from project memory, and why the file is untrusted input.
- [MCP](mcp.md) - why this repository ships no MCP servers, the binding tool-preference order
  every skill follows, the recommended minimal set, and why the strongest case for MCP here is
  authentication rather than capability.
- [Output discipline](output-discipline.md) - the canonical conciseness rules every skill
  inherits in its Expected Output Contract; what "menu, not checklist" means in practice.
- [Writing voice](writing-voice.md) - how everything a skill writes for a human reader
  should sound, the AI tells that are banned outright, the honesty boundary that voice
  rules must never cross, and the `ai_attribution` knob.
- [Insightful simplifications](insightful-simplifications.md) - the optional, bounded
  framing section any skill MAY add when one short architectural observation would help
  the user see the wider shape of the problem.
- [Token efficiency](token-efficiency.md) - principles, audit methodology, and current
  findings for keeping `agent-skills` cheap to load into agent context.
- [Assistant setup](assistants.md) - using the skills with common AI assistants.
- [Starter prompts](starter-prompts.md) - copy-paste prompts for single-skill and multi-skill work.
- [Examples](examples/README.md) - realistic input/output examples for each skill.
- [Validation](validation.md) - repository checks, warning/failure rules, and validation limits.
- [Skill quality scorecard](skill-quality-scorecard.md) - a simple 0-3 maintainer review aid.
- [Requirement-understanding workflow](requirement-understanding.md) - the twelve-step gate
  every relevant skill runs before implementation, review, testing, or automation.
- [Requirement-understanding scorecard](requirement-understanding-scorecard.md) - a 0-3
  maintainer aid for judging whether the agent understood the task before acting.
- [Skill performance review](skill-performance-review.md) - v0.8.0 manual review notes.
- [Eval runs](../eval-runs/README.md) - release-scoped scored sample runs.
- [Release checklist](release-checklist.md) - repeatable pre-release checks.
- [Plans](plans/2026-09-learning-voice-and-router.md) - the reviewed plan behind
  `v0.36.0`, kept as written next to its implementation status and the three items
  deferred pending a decision.
- [Skill boundaries](skill-boundaries.md) - ownership, handoffs, and nested-skill rationale.
- [Skill review loops](review-loops.md) - how producer skills hand off to reviewer skills
  with **bounded** revision rounds so the agent never spins forever.
- [Severity and confidence](severity-and-confidence.md) - shared review, defect, and investigation
  vocabulary.
- [Known limitations](known-limitations.md) - what the skills cannot guarantee.
- [Versioning](versioning.md) - release and compatibility policy.
- [Destructive-action safety policy](destructive-action-safety.md) - the safety floor every
  skill in this repository inherits; what an agent must never do autonomously, what counts as
  a discovered credential, and how human-controlled execution must work.
