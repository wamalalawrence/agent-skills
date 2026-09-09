# Security review — v1.0.0-rc.1 (release-candidate certification)

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.
This candidate ships no new feature, so this review re-attacks the existing boundaries rather
than assessing a new surface, and records what freezing the contracts commits to.

## Scope of this review

`v1.0.0-rc.1` changes: documentation (`SECURITY.md`, `ROADMAP.md`, `docs/versioning.md`,
`docs/updates.md`, new `docs/one-point-oh.md`); one message in `scripts/check-updates.py`; one
additional output line in `scripts/tools.py resolve`; and one channel-resolution change in
`scripts/install.py` (a `--dev` install falls back to the `any` channel instead of `stable`, so
installing a pre-release working tree is not refused — see below). No change to the release
provider, its channel gate, the archive-safety or integrity checks, the Access Resolver, the
Execution Guard engine, or the credential model. The threat model is the union of the prior
reviews, re-tested here end to end.

## Threat: the `--dev` channel-resolution change weakens downgrade / pre-release protection

**Probed + reasoned about.** `scripts/test-cli-install.sh` (new assertions), and the design.

`install.py` now resolves the effective channel as: an explicit `--channel` always wins; a
`--dev` install falls back to `any`; every other install falls back to `stable`, unchanged. The
change is scoped to `--dev`, which marks a development install of a local working tree — recorded
as such in the manifest and reported by `doctor`, never produced by `npx … install`.

- The **`stable` machine is unaffected**: `npx @wamalalawrence/agent-skills install` and
  `agent-skills update` never pass `--dev`, so they still resolve `stable` and are still never
  offered a pre-release.
- The **release-provider channel gate is untouched**. `resolve_latest("any")` was already the
  documented "install exactly this" path; `--dev` now reaches it, a plain
  `install --provider local --source …` still does not (asserted: a pre-release checkout is
  still refused without an explicit `--channel`).
- **Downgrade protection is unchanged** — `update` still refuses to move the active release
  backward without `--allow-downgrade`, `--dev` or not.

The residual is that a developer running `setup.init` on a checkout can install whatever version
that checkout declares. That was already true for `setup.init --home` and every existing dev
flow; `--dev` installs are explicitly not releases.

## Threat: instruction-shaped content is followed as an instruction

**Probed.** `scripts/test-guard.sh` (prompt-injection scenario, in 108), `scripts/test-context-optimizer.sh`
(untrusted-instruction-shaped flag), `scripts/test-tools.sh` §8, and a fresh RC probe set.

The RC probe planted `IGNORE ALL PREVIOUS INSTRUCTIONS … curl … | bash … DROP TABLE …` into a
ticket fixture, a log line, and around a failure, then:

- `context pack` kept the real failure line, **redacted** the session token embedded next to it,
  and ended the pack with the data-not-instructions contract line;
- `guard scan-content` classified the ticket as `SUSPICIOUS_*` — evidence for a reviewer, not a
  verdict;
- `guard check-command` denied the embedded `curl … | bash`, a nested-shell variant, a
  `psql … DROP TABLE`, and `terraform destroy` — all exit `20`.

The load-bearing guarantee is unchanged: steering may succeed at the reasoning layer, and the
resulting command still has to cross a deterministic gate.

## Threat: a READ capability performs a WRITE / ELEVATED / DESTRUCTIVE action

**Probed.** `scripts/test-tools.sh` §5 §11 §12, `scripts/test-tools.sh` bounded-note cases, and
the RC probe set (8 capability-escalation assertions).

The action class is fixed data in `lib/tools/capabilities.json`; `tools doctor` asserts the
vocabulary never contradicts its own suffix rules. `tools resolve`:

- returns a READ transport freely;
- refuses `WRITE` / `ELEVATED` without `--allow-write` (exit `2`);
- never returns a transport for `DESTRUCTIVE`, even with `--allow-write` (exit `2`);
- `--allow-write` on `database.query.read` leaves it `READ` — the flag cannot raise a class.

A skill that hand-assembles a mutating command under a READ capability is still caught by the
Execution Guard: the RC probe confirmed `DROP TABLE` via `psql` and `terraform destroy` are
denied regardless of how the framework classified the capability.

## Threat: repository-controlled data steers a machine credential; wrong account is selected

**Probed.** `scripts/test-access-resolution.sh` (100 assertions), `scripts/test-tools.sh` §4 §10.

A tool definition names a service, not an identity. Identity selection stays with
`agent-skills access bind` and a git-verified-untracked `.agent-skills.local.yml`. `tools.py`
passes only the definition's fixed `auth_service` string to `agent-skills access resolve`, and
the RC probe confirmed two different tools never share or cross a service name. The Access
Resolver's own rules — a committed file may not select a profile, a repo file may not supply a
host that disagrees with the identity, strict-binding, served-hosts scoping — are unchanged.

## Threat: a hostile release payload is activated

**Probed.** `scripts/test-release-engine.py` (21 checks).

Archive members with `..`, absolute paths, symlinks escaping the root, device/fifo nodes, and
setuid bits are rejected before a byte is written. A tampered payload, a payload whose `VERSION`
disagrees with the manifest, a payload that does not match the requested release, and a payload
symlink pointing outside the release are all refused with the integrity code (`5`). Pre-releases
sort below their release, so a downgrade cannot masquerade as an update. An unknown provider
name is a usage error, not a code-load path.

## Threat: a downgrade lands silently

**Reasoned about + probed.** `update` refuses to move the active release backward without
`--allow-downgrade` (`docs/updates.md`, asserted by `test-cli-install.sh`). `rc` is a superset
of `stable`, so an `rc` machine is still offered the stable release that supersedes the last
candidate — it cannot be pinned to pre-releases, and `stable` is never offered a pre-release at
all.

## Threat: a synthetic secret leaks into output

**Probed.** `scripts/test-private-source.sh` (token-shaped sweep across install / doctor /
verify / update / check / guard-install outputs and the written installation), the RC probe set
(GitHub-token, AWS-key, and session-token canaries through `tools status` / `inspect` /
`resolve`, `context pack`, `guard audit`, and a `guard check-command` on a `curl` carrying an
`Authorization: Bearer` header), and `scripts/test-context-optimizer.sh` redaction probes.

No canary appeared in any output. The Access Resolver reports only field *names*; `tools status`
and `resolve` report transport kinds, command names, and missing field names; the guard audit
log stores a redacted fingerprint, never a raw command line; `context pack` redacts
credential-shaped values before anything reaches the pack, the render, or the cache.

## Threat: the public npm bootstrap carries protected content

**Probed.** `scripts/audit-npm-package.sh`, a **release blocker**.

The `1.0.0-rc.1` tarball was audited: 14 files, the installation engine and `README` / `LICENSE`
only, no skills, no docs, no evals, no credential-shaped strings, no absolute developer paths,
no `preinstall` / `install` / `postinstall` / `prepare` script, and the vendored engine
byte-identical to `lib/asrelease/` and `scripts/install.py`. Package version equals `VERSION`.

The frozen contract — bootstrap and runtime move in lockstep, the bootstrap contains only the
installer — is what keeps this true for every future release: there is no version in which the
bootstrap could diverge from an audited installer.

## Threat: the bounded-read residual (carried from v0.44.0)

**Reasoned about.** The Engineering Tool Capability Framework *marks* a capability `bounded`; it
does not intercept the read. The v0.44.0 review recorded this as a residual.

For `1.0` the guarantee is layered and each layer is real and enforced where it can be:

1. **Marking correctness is runtime-enforced** — `tools doctor` fails (and `validate-repo.py`
   with it) if any `logs.read` / `query.read` / `message.sample` / `thread.read` /
   `document.read` / `errors.read` / `finding.read` / `timeline.read` / `traces.read` capability
   is missing from a tool's `bounded_capabilities`.
2. **The instruction now reaches the caller at the decision point**, not only in docs: `tools
   resolve` prints the explicit bound + `context pack` instruction for a bounded capability
   (new in this RC), and `software-engineer` / `issue-investigator` carry it in their workflow.
3. **The bounded read itself is deterministic and safe once `context pack` is used** —
   provenance, an exact budget, explicit omissions, credential redaction.

The unclosed part — a skill choosing not to call `context pack` — has no runtime interception
point, and adding one would require the framework to execute commands, which crosses the
"classifies, does not execute" line the design rests on. It is accepted for `1.0` as a residual
of the same class as "the guard cannot infer arbitrary interpreted-program behaviour" and "no
compression can prove the omitted content was irrelevant", and it is documented in
[engineering-tools.md](engineering-tools.md#known-limitations) and
[known-limitations.md](known-limitations.md).

## Residual risks

**A skill reads a bounded capability without calling `context pack`.**
Controls: the marking (runtime-enforced for correctness), the inline `tools resolve` instruction,
the skill workflows, and Context Optimizer itself once invoked. Not runtime-enforced at the read
because the framework does not execute.

**The `host` transport is asserted via `AGENT_SKILLS_TOOLS_ASSUME_HOST` but the host does not
expose the tool.** Opt-in, session-scoped; the default reports `host` as a step to check.

**JetBrains registration is not filesystem-verifiable.** Accepted and documented; `verify`
reports it as `manual` and a green `verify` is explicitly not evidence the IDE entry exists.

**Real-agent execution is proven only for the host this certification ran in (Claude Code).**
Contract and structural layers are proven for every host; interactive multi-agent execution on
the other hosts, and fully autonomous Wamala dispatch chains, are `UNPROVEN` pending a real
agent runner behind `scripts/run-evals.py --invoke`.

## What this review does not establish

- It does not integration-test any reference tool against a live vendor instance.
- It does not prove the capability vocabulary is complete — `data_pipeline.*`, `design.*`, and
  `security.*` ship with vocabulary and design only. Freezing the names does not require a
  validated tool; adding one later is a compatible change.
- It is not an OS sandbox or an IAM control. Scoped credentials, read-only roles, and network
  policy remain the stronger controls, unchanged.
