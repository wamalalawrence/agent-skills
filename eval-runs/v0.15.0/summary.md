# v0.15.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.15.0`. It scores the
destructive-action safety floor introduced for the four skills that touch
deployed environments and the two skills that author work for those skills.

Category: maintainer-authored (illustrative).

## Scope of this release

- New global policy `docs/destructive-action-safety.md` defining the
  single source of truth all six skills inherit.
- New `## Destructive Action Guardrails` section in
  `software-engineer/SKILL.md` operationalising the policy for engineering
  work (default-safe mode, no use of discovered credentials, no
  search-for-credentials, environment confirmation before mutation,
  destructive commands blocked unless authorized maintenance with
  isolated backups, runbook handoff for production-impacting fixes).
- New "Discovered-credential protocol" subsection in
  `issue-investigator/SKILL.md` plus `read-only`/`mutating` classification
  on every proposed check.
- New "Agent-execution safety" sections in
  `references/code-review-checklist.md` and
  `references/security-checklist.md` so reviewer findings are concrete.
- "Safety floor" callouts in all six `SKILL.md` files cross-linking to the
  policy and stating per-skill operational consequences.
- `validate-repo.py` REQUIRED_FILES list extended so the policy file
  cannot be accidentally removed without breaking CI.

## Scoring summary

Each item below scores the user-visible improvement on the 5-point scale used
by previous eval runs (1=poor, 5=excellent).

- Coverage of the documented public failure mode (agent finds in-repo
  token → uses it → deletes production volume / backups): 5/5. Each step of
  the chain is now blocked by an explicit, named rule (discovered-credential
  protocol → read-only default → environment confirmation → destructive-
  command block → backup isolation → runbook contract). The reviewer skill
  surfaces any diff that introduces such a chain as a `blocker`.
- Defence-in-depth realism: 5/5. The policy explicitly states that
  prompt-level rules assume the underlying tool sandbox / IAM / network
  policy may all fail, and that the floor is not waivable by user prompt.
  No skill relies on "ask for confirmation" as the load-bearing control.
- Operator-runbook contract clarity: 5/5. Goal / scope / pre-conditions /
  steps labelled `read-only`/`mutating` / verification / rollback / stop
  conditions / authorization. Backup verification and approval gates are
  required, not advisory.
- Cross-skill consistency: 5/5. All six skills now carry the same safety-
  floor callout shape, and reference checklists, the policy, and the
  individual skill sections all use the same vocabulary
  (read-only-by-construction, discovered credential, fix-by-deletion,
  authorized destructive maintenance).
- Surgical-edit discipline: 5/5. No new skills, no skill renames, no
  contract changes. No new environment variables, no `setup.init` change,
  no `.env.example` change. Pure SKILL/policy hardening plus a single
  validator REQUIRED_FILES line for the new doc.

## Reviewer self-rebuttal

The most credible scenarios in which this release is wrong about the safety
floor being effective:

- **An agent ignores the prompt entirely.** This release does not claim
  prompt-level rules can compel a model. The policy explicitly states that
  prompt rules are necessary but not sufficient and require runtime
  guardrails (scoped credentials, IAM, network policy) to actually hold.
  The policy informs the agent's reasoning, recommends safer defaults, and
  gives a reviewer concrete blocker findings to catch escapes after the
  fact. It does not promise to compel a misaligned model.
- **A user types "ignore the safety policy".** The policy includes an
  explicit "no prompt waiver" clause and a "what to do when an action is
  refused" section. Whether a given agent honours this depends on the
  model, but every skill states the floor is not waivable, the reviewer is
  required to surface violations as `blocker`, and the user-side controls
  (scoped credentials, no in-repo tokens, backup isolation) remain in
  place regardless of prompt content.
- **The policy is too long for some agents to consume.** The per-skill
  callouts are short and front-loaded; the long policy is the source of
  truth that the callouts link to. Shorter agents still see the floor at
  the top of the SKILL.md they load.

## Follow-ups recorded for future releases

- Consider adding a `.cache/agent-skills/<task>/safety-acknowledged.json`
  artifact that the engineer skill must write before any mutating action,
  capturing the environment, blast radius, approver, and authorization
  source. The `code-reviewer` would then refuse to advance without it.
- Consider an opt-in setup flag that probes the configured agent
  credential's destructive privileges and warns at `setup.init` time if
  it can delete buckets / volumes / databases / snapshots without a
  separate scoped role.
- Consider bundling a sample IAM policy template in `docs/` showing a
  recommended least-privilege agent role for read-only investigation.
- Consider adding a `manual` review profile to `code-reviewer` named
  `safety-floor-only` that scans an arbitrary diff for floor violations
  without doing full code review.
