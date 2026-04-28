# v0.16.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.16.0`. It scores
the two enforcement artifacts that reinforce the `v0.15.0` destructive-
action safety floor: the `safety_acknowledgement` block in
`definition-of-done.json` and the warn-only credential blast-radius probe
in `setup.init`.

Category: maintainer-authored (illustrative).

## Scope of this release

- `safety_acknowledgement` block added to the `definition-of-done.json`
  schema and required when the change introduces or performs any
  mutating action against a deployed environment, or touches
  credentials / IAM / secrets / backups / monitoring / network policy.
- `code-reviewer` hard handoff contract updated to surface a `blocker`
  finding when the block is missing-on-required, when a discovered or
  in-repo credential was invoked, when a destructive command was used
  without a populated authorization, when `execution_path: agent` for a
  destructive/IAM/secret/backup change, or when
  monitoring/IAM/network-policy was changed without a written waiver.
- `setup.init` warn-only credential blast-radius probe that flags
  destructive-capable cloud / orchestrator / database credentials in the
  shell or `.env` and recommends scoping to a least-privilege role.
- `docs/destructive-action-safety.md` gains an "Enforcement artifacts"
  section linking the two artifacts to the policy.
- No new skills, no skill renames, no new required env vars, no
  `.env.example` change.

## Scoring summary

- Reviewer enforcement of the safety floor: 5/5. The artifact is now
  structured (booleans, named fields), not prose. The reviewer's
  blocker conditions are explicit. A diff that touches a deployed
  environment cannot reach `PASS` without a truthful acknowledgement.
- Operator-time warning surface: 5/5. The probe runs at the moment the
  operator is most likely to act (during setup, and again on every
  `--verify`). It names the offending variables and the recommended
  scope.
- Honest about probe limits: 5/5. The probe is heuristic; it cannot
  inspect cloud-provider IAM policies. The CHANGELOG and policy doc
  state this plainly. The probe does not block setup, does not fail
  CI, and does not touch state.
- Surgical-edit discipline: 5/5. No new skills, no skill renames, no
  new required env vars. The new flag (`--no-credential-probe`) mirrors
  the existing `--no-connectivity-check` shape.
- Public-good portability: 5/5. Probe variable names are generic
  cloud-provider names; no vendor-specific products, no real tokens.

## Reviewer self-rebuttal

- **The reviewer can be lied to.** The `safety_acknowledgement` block
  is engineer-authored. A misaligned engineer could mark
  `no_discovered_credentials_invoked: true` falsely. This is true and
  is the same trust model as every other field in
  `definition-of-done.json`. The reviewer mitigates by cross-checking
  against the diff: invocation of credentials read from repo files,
  destructive cloud commands, IAM/network/secret changes, and missing
  blocks on diffs that obviously require one are all `blocker` findings
  regardless of what the field says. The block is the gate; the diff
  is the source of truth.
- **The probe will false-positive in legitimate setups.** Some teams
  legitimately use long-lived AWS keys for CI. The probe is warn-only
  and prints the recommended scoping. Operators who have already
  scoped down their role will see a one-line WARN and can ignore it,
  or skip the probe with `--no-credential-probe`. The cost of the
  false positive is one paragraph of output; the cost of missing the
  case is the `v0.15.0` failure mode.
- **The probe cannot prove scoping.** Stated explicitly in the
  output ("heuristic; cannot inspect cloud-provider IAM policies —
  confirm scoping in your provider console") and in the policy.

## Follow-ups recorded for future releases

- A `safety-floor-only` review profile in `code-reviewer` for scanning
  arbitrary diffs against the floor without full code review.
- A sample IAM policy template under `docs/` showing a recommended
  least-privilege agent role for read-only investigation.
- Optional CI step that re-runs the credential probe against the CI
  runner's environment so destructive-capable runner secrets get the
  same warning surface as local setup.
- Consider extending the probe to detect kubeconfig contexts whose
  `cluster.server` URL points at a known production-shaped hostname
  (heuristic, opt-in).
