# Roadmap

`agent-skills` is a private, solo-maintained project. It grows through proven usefulness in the
maintainer's own delivery work, not through an up-front framework.

## Commercial direction — decided September 2026

The next product initiative is a single per-developer subscription: **€11 per named developer per
month**, bought by individuals or by companies for a number of seats, with an account portal and
private release distribution that needs no customer GitHub access. The
[commercial subscription and distribution plan](docs/commercial-roadmap.md) is final — the stack,
the billing and licensing behaviour, the operating costs, the test matrix, and a fourteen-phase
build order through controlled beta to public launch. Nothing in it is blocked on a further
decision. Phase 00 is the next task. It is a plan, not a shipped capability.

Foundation: one Cloudflare Worker with Static Assets, Better Auth, Neon PostgreSQL, private R2,
Stripe with Managed Payments, Resend, and GitHub Actions. Licensing is enforced at the
distribution boundary only — an active seat is required to download and update, and nothing in
the installed runtime blocks work. The commercial line ships as `2.0`; `1.x` keeps every frozen
contract and its current credential-free install path.

## Now: v1.1.0

A field-report release on top of `1.0.0`. Wamala finishes multi-phase runs on hosts where
dispatched agents cannot dispatch, routes a defective plan to its planner, restores independent
review one level up, carries each phase's `follow_up_context` into the next brief, and checks a
delete before it happens. The lifecycle wrappers keep what a step produced, take the flags their
own error message names, and agree on one cache. Additive against the 1.0 contract; see the
changelog. The npm bootstrap moves in lockstep to `1.1.0`.

## Previously: v1.0.0

The first stable release. The [1.0 contracts](./docs/one-point-oh.md) — CLI command names,
arguments, exit codes, and machine-readable output; the versioned install layout, `current`
activation, and update/rollback semantics; the release-provider interface; the skill names and
Wamala's routing model; the tool capability vocabulary and tool-definition schema — are frozen
for the `1.x` line. Breaking changes wait for `2.0`.

What `1.0.0` itself changed, on top of the four release candidates: the boundary between what an
agent claims and what the runtime records. A lesson's confidence rises only on distinct
evidence; a contradiction disputes it rather than refreshing it; recall honours its budget with
the frame included; a closeout is recorded as verified only when a `definition-of-done.json`
survives `dod-check`; the stop-hook fallback is a no-op after a normal finish; two phases whose
mutation targets are a parent and a child are no longer "provably independent". See the
changelog and [evidence discipline](./docs/evidence-discipline.md).

Published as a GitHub release. The npm bootstrap `@wamalalawrence/agent-skills@1.0.0` goes to the
`latest` dist-tag, which resolves the stable-line question this roadmap carried through the
candidate series: `latest` had been pinned at `0.43.0` while the newest stable runtime was
`0.44.0`. The registry account requires a one-time password, so that publish is the one release
step no automation performs — the maintainer runs `npm publish` after the tag, against the
audited tarball. From here the bootstrap and the runtime move in lockstep: one version number,
published together.

## 1.x

- **A release-level behavioural suite.** The eval corpus validates scenarios, not behaviour.
  Record actual tool trajectories for the properties the deterministic suites cannot hold —
  a missing RED test, a forged green artifact, a stale evidence revision, a planted instruction
  in a memory file, an ambiguous scope — grade the observable state deterministically, pin the
  model and host, and run it on release candidates rather than on every pull request. This is
  the roadmap item behind [`run-evals.py --invoke`](./scripts/run-evals.py).
- **Entry-point size.** `software-engineer` runs to 1,300 lines, `code-reviewer` and
  `issue-investigator` to 850 each. The dispatcher no longer loads them, but activating one is
  still a cost. Split task-specific detail into directly linked phase references and keep every
  safety and transition rule in a small always-loaded core. Measure context volume and task
  quality before and after; do not cut obligations to hit a line count.
- **Revision-aware memory maintenance.** Check a lesson's cited file or revision lazily when it
  is retrieved, so a five-minute-old fact invalidated by a commit does not wait ninety days for
  decay. Bounded and on demand; no always-running librarian.
- Read release-time telemetry — in particular the share of `completed` closeouts with
  `verified_delivery=no` — to decide which nested skills, if any, should become top-level.
- Fill the capability families that ship with vocabulary and design only —
  `data_pipeline.*`, `design.*`, `security.*` — with a validated reference tool each, when a
  real workflow needs one. Adding a capability is a compatible change; renaming or reclassifying
  one is not.

## Later

- The subscription release provider is specified in phase 12 of the
  [commercial plan](docs/commercial-roadmap.md); implementation has not started.
- Additional top-level role skills only when there is real workflow content to justify them.
- A vector store for recall, only if keyword and source-based retrieval is shown to miss
  relevant lessons at a real knowledge-base size. Not before the misses are measured.

## Non-goals

- No `develop` branch or GitFlow. `main`, short-lived branches, pull requests, version tags.
- No meeting intelligence or general analytics dashboard. The commercial account, billing, and
  seat portal is the one bounded UI exception, scoped in the [commercial plan](docs/commercial-roadmap.md).
- No mandatory interrogation step before every task; the requirement gate already asks only
  when an answer changes behaviour, authorization, scope, or an irreversible decision.
- No company-specific workflow bundles in this repository.
