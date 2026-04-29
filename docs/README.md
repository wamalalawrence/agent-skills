# Documentation

Start here when reading the repository outside GitHub's main README.

- [Quickstart](quickstart.md) - first practical path through setup and skill use.
- [Installation](installation.md) - local-workspace and in-repo setup.
- [Configuration](configuration.md) - environment and project metadata.
- [Execution modes](execution-modes.md) - how skills choose local-workspace vs in-repo mode.
- [Jira / Confluence auth discovery](auth-discovery.md) - the order skills must walk before
  declaring auth unavailable, how `${VAR}` placeholders are resolved, the auth preflight
  script, and the troubleshooting table for common failures.
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
- [Skill boundaries](skill-boundaries.md) - ownership, handoffs, and nested-skill rationale.
- [Severity and confidence](severity-and-confidence.md) - shared review, defect, and investigation
  vocabulary.
- [Known limitations](known-limitations.md) - what the skills cannot guarantee.
- [Versioning](versioning.md) - release and compatibility policy.
- [Destructive-action safety policy](destructive-action-safety.md) - the safety floor every
  skill in this repository inherits; what an agent must never do autonomously, what counts as
  a discovered credential, and how human-controlled execution must work.
