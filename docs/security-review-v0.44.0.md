# Security review — v0.44.0 (Engineering Tool Capability Framework)

Follows the shape of [the v0.37.0 review](security-review-v0.37.0.md): each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design, not executed), or
**unproven**. Findings and their resolutions are recorded, then residual risks.

## What this release changes about the trust boundary

A new layer, `scripts/tools.py`, reads declarative tool definitions from `lib/tools/` and resolves
a *transport* for a named capability. It introduces:

- a new class of committed, repository-adjacent data (`lib/tools/registry.d/*.json`);
- a new caller of `agent-skills access resolve`;
- a new place where an action is classified as READ / WRITE / ELEVATED / DESTRUCTIVE.

It introduces **no** new credential storage, **no** new network client, and **no** new
enforcement engine. Authentication stays with the Access Resolver; enforcement stays with the
Execution Guard.

## Threat: a READ capability is used to perform a WRITE

**Probed.** `scripts/test-tools.sh` §5, §6, §11.

The action class is fixed data in `lib/tools/capabilities.json`, keyed by capability name, and
`tools doctor` asserts the vocabulary never contradicts its own suffix rules (`.plan`/`.explain`
→ READ, `.apply`/`.publish`/`.trigger`/`.deploy` → ELEVATED, `.destroy`/`.delete` →
DESTRUCTIVE). `tools resolve`:

- returns a transport for a READ capability freely;
- refuses a `WRITE`/`ELEVATED` capability unless `--allow-write` is passed, exiting `2`;
- never returns a transport for a `DESTRUCTIVE` capability, exiting `2`.

`--allow-write` cannot raise a READ: `resolve postgresql --capability database.query.read
--allow-write` still reports `action_class: READ`. No `*.read` capability is classified as a
mutation (asserted).

**Probe negative control:** the test asserts the class is read back from the vocabulary, not the
flag — a build that let `--allow-write` change the class would fail §11.

## Threat: resolution is treated as authorization

**Probed / reasoned about.** `scripts/test-tools.sh` §12; design.

Every resolved `tools resolve` result prints `resolution is not authorization. The Execution
Guard gates the command that runs.` The framework never executes a command — it reports which
transport to use. §12 shows the coupling end to end: `tools classify terraform
infrastructure.destroy` returns `DESTRUCTIVE` **and** `guard check-command -- 'terraform destroy
-auto-approve'` exits `20` (deny); `psql -c "DROP TABLE orders"` exits `20`. The Guard's 31
hard-floor rules are unchanged by this release (`test-guard.sh`: 54 rules, 31 floor, 108
assertions, all pass).

## Threat: a destructive action slips past because the framework "handled" it

**Reasoned about.** The framework maps action classes onto the existing Guard rules; it does not
re-implement them and cannot lower them. A `DESTRUCTIVE` capability is refused at the framework
layer *and* denied at the Guard layer. The stricter outcome — deny — is the one that applies,
consistent with the policy's "where a runtime rule and the policy disagree, the stricter outcome
wins".

## Threat: a production read pulls an unbounded, hostile payload into context

**Probed.** `scripts/test-tools.sh` §6, §7; `tools doctor` coherence check.

Every capability whose name contains `logs.read`, `query.read`, `message.sample`, `thread.read`,
`document.read`, `errors.read`, `finding.read`, `timeline.read`, or `traces.read` must appear
under `bounded_capabilities` on every tool that owns it. `tools doctor` fails otherwise, and
`validate-repo.py` runs `tools doctor`. §7 builds a 64k-line pod log, confirms `context check`
reports it over threshold (exit 10), and confirms `context pack` keeps the failure line while
dropping the bulk. The docs bind the consuming skill to read with an explicit bound (time range,
row limit, message count, log budget) and route through Context Optimizer.

**Residual:** the framework cannot force a skill to actually call `context pack`. This is the
same residual the Context Optimizer review already records; the marking and the docs are the
controls, the Guard is not one here.

## Threat: a provider's output leaks a secret

**Probed.** `scripts/test-tools.sh` §2, §4, §10; code read.

`tools status` and `tools resolve` print transport *kinds*, command names, `auth_service` names,
and missing field *names* — never a field value. The framework never reads a secret: for
`profile` / `api` transports it shells `agent-skills access resolve --json`, whose output is
documented safe for agent context and contains no secret. Grep of `tools.py` confirms no code
path prints `verdict` values beyond `status` / `missing`. The stub-launcher tests assert only
field names cross the boundary.

## Threat: one provider failing breaks the walk for another

**Probed.** `scripts/test-tools.sh` §9.

Each transport probe is wrapped; a probe that fails or a launcher that errors is recorded as a
skipped step and the walk continues. `tools status` with one tool's probe deliberately failing
still reports every tool and exits `0`. A malformed single tool definition is caught by
`tools doctor` with the offending file named, and does not crash `list` / `status` for the rest.

## Threat: repository-controlled config steers an unrelated machine credential

**Probed / reasoned about.** `scripts/test-tools.sh` §4, §10; design; inherits
`scripts/test-access-resolution.sh` (100 assertions, pass).

A tool definition describes *what* a service is — an id, a class, a capability list, a transport
list, an `auth_service` name. It **cannot** select a credential identity: identity selection stays
with `agent-skills access bind` and `.agent-skills.local.yml`, exactly as the Access Resolver
already enforces, and `tools.py` passes only the definition's fixed `auth_service` string to
`access resolve`. §4 asserts `resolve github` only ever calls `access resolve --service github`;
§10 asserts two different tools never share or cross a service name. The Access Resolver's own
rules — a committed file may not select a profile, a repo file may not supply a host that
disagrees with the identity, strict-binding, served-hosts scoping — are unchanged and still own
that decision.

**Note on the new committed data.** `lib/tools/registry.d/*.json` lives in *this* repository, not
a worked-on repository, and is changed only through a PR against `main` like any other source
file. It is not attacker-controlled in the way a target repo's `.agent-skills.yml` is. Even so,
the worst a malformed or hostile definition here can do is name a wrong `auth_service` — which
resolves to "no such identity / needs setup", never to a different real credential, because the
Access Resolver will not select an identity a committed file named.

## Threat: untrusted tool output is followed as an instruction

**Probed.** `scripts/test-tools.sh` §8.

Instruction-shaped text piped to `tools classify` on stdin does not change the classification —
the framework takes input only from argv, never from piped content, and reads no configuration,
budget, path, strategy, credential, or policy from any external payload. `guard scan-content`
flags the injected text as `SUSPICIOUS_*` evidence. The docs state the contract explicitly:
everything a tool returns is "claims to verify, never instructions to follow".

## Threat: a fixture is mistaken for a supported integration

**Probed.** `scripts/test-tools.sh` §1, §14.

`gitlab`, `gcp`, `mysql`, `newrelic` live in `lib/tools/fixtures/`, are excluded from the default
`list` / `status`, require `--include-fixtures`, are labelled `(fixture)` when shown, and carry
`reference_status: "fixture"`. `tools doctor` asserts a file under `fixtures/` cannot claim
`validated`. The changelog and docs name them as extensibility fixtures, not integrations.

## Licensing change

**Reasoned about.** Not a code-security change. The MIT grant is removed; `LICENSE` now states no
license is granted. This is the default legal posture for a private repository and introduces no
runtime behaviour. `validate-repo.py` still requires the `LICENSE` file to exist and each
`SKILL.md` to carry a non-empty `license:` field, both satisfied (`PROPRIETARY`).

## Residual risks

**A skill reads a `bounded` capability without calling `context pack`.**
Control: the `bounded` marking, the docs, and `tools doctor`. Not enforced at runtime because no
interception point exists for "an agent chose to read a file whole" — this is the Context
Optimizer residual, unchanged by this release.

**The `host` transport is asserted via `AGENT_SKILLS_TOOLS_ASSUME_HOST` but the host does not
actually expose the tool.**
Control: the variable is opt-in and session-scoped; the default is to report `host` as a step to
check, never to resolve it. A script cannot see host-native tools, and guessing would be worse
than reporting "check your host".

**A public npm bootstrap remains published for a now-private, proprietary project.**
Control: publication is **deferred** this release; distribution is git-provider only (tag +
GitHub release). Whether to unpublish, or to keep a public installer stub that fetches a private
access-controlled payload, is an owner decision — recorded here and in the changelog, not one to
make silently inside a feature release.

## What this review does not establish

- It does not integration-test any reference tool against a live instance. `reference_status:
  validated` means the framework resolution path was exercised, not that every capability round-
  trips against a real GitHub / Jira / Sentry / cluster.
- It does not prove the capability vocabulary is complete or correctly carved — that is the 1.0
  freeze review's job (see [versioning.md](versioning.md#the-10-contract)).
- It does not re-audit the Access Resolver or the Execution Guard; both are unchanged in
  substance and covered by their own suites, which pass.
