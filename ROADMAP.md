# Roadmap

`agent-skills` is a private, solo-maintained project. It grows through proven usefulness in the
maintainer's own delivery work, not through an up-front framework.

## Now: v1.0.0-rc.1

v0.44.0 shipped the last substantial feature — the
[Engineering Tool Capability Framework](./docs/engineering-tools.md). The work from here is
**certification and contract freeze**, not features:

- Freeze the contracts the project will support after 1.0: the CLI command names, arguments,
  exit codes, and machine-readable output; the versioned install layout, `current` activation,
  and update/rollback semantics; the release-provider interface; the skill names and Wamala's
  routing model; the tool capability vocabulary and tool-definition schema. Frozen set:
  [docs/one-point-oh.md](./docs/one-point-oh.md).
- Certify a clean-machine install from the private release source (authenticated succeeds,
  unauthenticated fails cleanly), upgrade/rollback with no mixed-version state, and preservation
  of credentials, bindings, knowledge, and unrelated host state.
- Re-run the full test, eval, and red-team harness; complete a security review.
- Publish `v1.0.0-rc.1` as a GitHub prerelease and an npm bootstrap on the `rc` dist-tag —
  never moving `latest` to the release candidate.

## After 1.0.0

- Move `latest` (GitHub release and npm dist-tag) to `1.0.0` once the RC has been exercised.
- Keep bootstrap and runtime versions in lockstep: one version number, published together.
- Maintain the frozen contracts within the major version; breaking changes wait for 2.0.
- Read release-time telemetry to decide which nested skills, if any, should become top-level.
- Fill the capability families that ship with vocabulary and design only —
  `data_pipeline.*`, `design.*`, `security.*` — with a validated reference tool each, when a
  real workflow needs one. Adding a capability is a compatible change; renaming or reclassifying
  one is not.

## Later

- A subscription release provider (`lib/asrelease/providers/`) — a new file, not a rewrite of
  installation. Not started.
- Additional top-level role skills only when there is real workflow content to justify them.
- Wire a real agent runner behind [`scripts/run-evals.py`](./scripts/run-evals.py) `--invoke` so
  the eval harness produces a measured pass/fail per skill per release.

## Non-goals

- No `develop` branch or GitFlow. `main`, short-lived branches, pull requests, version tags.
- No meeting intelligence, dashboard, or UI.
- No premium registry or subscription system before 1.0.
- No company-specific workflow bundles in this repository.
