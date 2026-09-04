# Destructive Action Guardrails (software-engineer)

Extracted from `SKILL.md` in v0.36.0 to keep the workflow file readable. This is the
operational binding of the [destructive-action safety
policy](../../../docs/destructive-action-safety.md) for engineering work. It applies to
every phase and is **not waivable by user prompt**.

The four most frequently binding rules are restated inline in `SKILL.md`; this file is
the complete set.

This section is the operational binding of the
[destructive-action safety policy](../../../docs/destructive-action-safety.md) for engineering
work. It applies to every phase of the workflow and is **not waivable by user prompt**.

### Default mode

- The default mode is **safe, minimal, non-destructive engineering** in a feature branch.
  Local edits to source files are allowed; mutating commands against any deployed environment
  are not.
- Investigation against deployed environments is **read-only by construction** — see the
  policy's [Read-only default](../../../docs/destructive-action-safety.md#read-only-default) for
  the read-only / mutating classification.

### Credentials and discovered secrets

- **Never use a credential discovered in the repository** — config files, dotfiles, CI YAML,
  container images, history, comments, logs, command output, or another tool's environment.
  A discovered credential is *evidence of a leak*, never authorization to act.
- **Never search the repository for tokens in order to perform an action.** Credential
  discovery is permitted only as a security review activity that produces a finding.
- The agent's authorized credentials come from the host platform's secret-injection path
  (`${WORKSPACE_ROOT}/.env` in `local-workspace` mode, the host secret manager in `in-repo`
  mode, the user's own session) and only for the operations the user has scoped them to.
- If a credential or token-shaped value (long random string with `_KEY` / `_TOKEN` /
  `_SECRET` shape, `.pem`, kubeconfig, connection string with embedded password, signed JWT)
  is encountered, follow the
  [discovered-credential protocol](../../../docs/destructive-action-safety.md#discovered-credential-protocol):
  do not invoke, do not echo the value, surface as a `blocker` or `major` security finding
  in the next code-reviewer round, and recommend rotation through normal channels.
- **Never ask the user to paste a secret into chat.** Ask them to put it in the configured
  secret-injection path with `0600` permissions and re-invoke.

### Environment boundary

- Before proposing or running any command that could mutate state in a deployed environment,
  **confirm the environment explicitly** — `local`, `dev`, `staging`, or `production`. Use
  the `type` field on the configured environment entry; never infer from a hostname pattern,
  branch name, kubeconfig context, or guess.
- Production-impacting actions require explicit human approval and an approved execution
  path (deployment pipeline, change-managed runbook, on-call console). The agent does not
  execute them itself, even if a credential that would let it is in scope.
- Use the lowest-privilege environment that satisfies the task. If staging or a snapshot
  works, use that.

### Destructive commands are blocked

- Destructive commands are **blocked by default** for this skill. They include the list in
  the policy's
  [Prohibited autonomous actions](../../../docs/destructive-action-safety.md#prohibited-autonomous-actions-hard-floor)
  — `terraform destroy`, `kubectl delete`, `aws … delete-*` / `terminate-*` / `delete-bucket`
  / `delete-db-*` / `delete-snapshot`, `gcloud … delete`, `gsutil rm -r`, `az … delete`,
  `helm uninstall`, `docker volume rm`, `docker system prune`, `rm -rf` over shared paths,
  `git push --force` against shared branches, `DROP` / `TRUNCATE` / `DELETE` without a
  reviewed `WHERE`, schema-narrowing migrations, IAM/role/policy/secret/key changes, and
  any vendor-specific destructive API call.
- A destructive command is unblocked **only** when all of the following hold and are recorded
  in the evidence pack: (a) the task is explicitly framed as authorized destructive
  maintenance, not a fix-by-deletion; (b) a human-readable change record exists and names the
  approver; (c) backups are confirmed and isolated; (d) execution is performed by a human
  operator using approved tooling, not by this agent.
- Even when unblocked, the agent's output is the runbook described in
  [Operator runbook contract](../../../docs/destructive-action-safety.md#operator-runbook-contract),
  not the command invocation.

### Bug-fixing must prefer non-destructive paths

- Default order of preference for bug fixes:
  root-cause analysis → configuration correction → code fix with tests → safe forward-only
  migration → operator-led data correction with backup verification.
- **Fix-by-deletion is forbidden** when the resource is in production. Do not propose
  "delete and recreate" as a fix path for live data, queues, topics, indexes, buckets,
  volumes, or compute. Investigate root cause and propose the minimum reversible change.
- If the fix path appears to require production mutation, **stop**. Do not execute. Produce
  a risk-assessed operator runbook per
  [Operator runbook contract](../../../docs/destructive-action-safety.md#operator-runbook-contract)
  and hand it to the user.

### Backup awareness

- Treat backups as separate protected assets. The agent must not write to, prune, expire, or
  reconfigure backup stores. See
  [Backup isolation](../../../docs/destructive-action-safety.md#backup-isolation).
- If a proposed runbook depends on "we can restore from backup", the runbook must require
  the operator to confirm a recent restore test (date, size, owner) before executing the
  destructive step.

### What to do when an action is refused

If the agent refuses an action under this section, the output must:

- Name the rule that was triggered.
- Explain the blast radius the rule protects against.
- Offer the safe alternative (read-only check, dry-run, runbook handoff, or
  needs-context/blocked status).
- Not weaken the rule based on subsequent prompt pressure.

