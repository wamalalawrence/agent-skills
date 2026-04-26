# Known Limitations

`agent-skills` provides instructions and workflows. It does not provide deterministic software,
runtime enforcement, or guaranteed outcomes.

- **Agent behavior varies.** Different assistants may follow the same `SKILL.md` with different
  levels of consistency, especially for nested skills.
- **Nested skill support is tool-dependent.** Some agents may not automatically discover or follow
  `software-engineer/skills/issue-investigator` and `software-engineer/skills/code-reviewer`. In those
  cases, attach or reference the nested `SKILL.md` directly.
- **External access depends on your tools and permissions.** Jira, GitHub, Confluence, CI, logs, and
  cloud environments are only available when your agent session has the right credentials and network
  access.
- **Company-specific standards are not bundled.** Repository conventions, coding standards, ticket
  formats, review rules, deployment practices, and architecture constraints must come from the user,
  the target repository, or attached documentation.
- **Generated output requires human review.** Plans, code, tests, acceptance criteria, defect
  reports, and reviews should be checked by a responsible human before use.
- **Evidence-pack and cache flows depend on the execution environment.** Local-workspace mode,
  in-repo/cloud-agent mode, ephemeral runners, and web agents may differ in what files they can read,
  write, or preserve between turns.
- **No warranty or SLA.** This project offers no guaranteed correctness, availability, response
  time, support commitment, or fitness for a particular purpose.
