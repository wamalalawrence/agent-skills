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
  access. See [auth-discovery.md](auth-discovery.md) for the documented discovery order skills must
  walk before reporting Jira / Confluence as unavailable; agents that skip the walk will report
  "no auth" when the real cause is unloaded `.env` or unresolved `${VAR}` placeholders.
- **Company-specific standards are not bundled.** Repository conventions, coding standards, ticket
  formats, review rules, deployment practices, and architecture constraints must come from the user,
  the target repository, or attached documentation.
- **Generated output requires human review.** Plans, code, tests, acceptance criteria, defect
  reports, and reviews should be checked by a responsible human before use.
- **Evidence-pack and cache flows depend on the execution environment.** Local-workspace mode,
  in-repo/cloud-agent mode, ephemeral runners, and web agents may differ in what files they can read,
  write, or preserve between turns.
- **Skill-source ambiguity is the operator's call.** When a workspace has more than one
  on-disk skill source (`.skills`, a vendored `.agent-skills/skills`, or the source clone),
  the agent walks the resolution order in [skill-source-resolution.md](skill-source-resolution.md)
  and asks if no winner is determined. It will not silently merge or pick.
- **No warranty or SLA.** This project offers no guaranteed correctness, availability, response
  time, support commitment, or fitness for a particular purpose.
