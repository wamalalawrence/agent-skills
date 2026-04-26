# Roadmap

This roadmap is intentionally modest. `agent-skills` is a solo-maintainer public-benefit project, so
the project should grow through proven usefulness rather than a large up-front framework.

## Current Focus

- Stabilize the four core delivery skills: [`product-owner`](./skills/product-owner/),
  [`software-engineer`](./skills/software-engineer/), [`manual-tester`](./skills/manual-tester/),
  and [`test-automation-engineer`](./skills/test-automation-engineer/).
- Keep [`software-engineer`](./skills/software-engineer/) strong as the flagship engineering skill.
- Improve portability across different stacks and workspace layouts.
- Tighten token-efficient context gathering for Jira, user descriptions, repository discovery,
  product refinement, testing, and review loops.
- Collect real-world feedback on where nested skills should remain nested or become standalone
  roles.

## Near-Term

- Add practical examples for installing and invoking skills in common AI coding assistants.
- Add examples that show cross-skill handoffs across product definition, engineering, manual
  testing, and automation.
- Add a lightweight validation script for skill frontmatter, required sections, and hardcoded
  organization-specific strings.
- Improve contribution examples for new reference checklists and nested skills.
- Keep known limitations and compatibility notes current as users report them.

## Later

- Consider additional top-level role skills, such as `software-architect` or `release-manager`, only
  when there is enough real workflow content to justify them.
- Explore packaging or release automation if manual releases become painful.
- Add issue and pull request templates when community volume justifies them.
- Invite additional maintainers if the project develops sustained external contribution.

## Non-Goals For Now

- No large governance structure before there is a contributor base.
- No `develop` branch or GitFlow process. Use `main`, short-lived feature branches, pull requests,
  and version tags.
- No package registry or installer until the manual folder-based setup is well understood.
- No company-specific workflow bundles in this repository.
- No promise that every planned role in the README will be built immediately.
