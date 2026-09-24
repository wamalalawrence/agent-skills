# Engineering Tool Capability Framework

A developer's day touches source control, a tracker, a knowledge base, chat, a cluster, a cloud,
a CI system, a database, a broker, a package registry. Agent Skills should be able to use those
tools as evidence and as leverage — without a bespoke adapter for every vendor, and without
turning the [Access Resolver](access-resolution.md) into a switch statement with one arm per
product.

This framework is the layer that makes that work. It is **infrastructure, not a skill**: like the
Access Resolver and [Execution Guard](execution-guard.md), nothing routes work *to* it. A skill
names a capability; the framework decides how that capability can be provided on this machine.

```text
Engineering task
      |
      v
Skill                         decides WHAT engineering work is needed
      |
      v
Required capability           e.g. ci.logs.read, database.query.read, infrastructure.plan
      |
      v
Engineering Tool Resolver     decides HOW the capability can be provided
      |
      +-- host-native tool
      +-- MCP server the host already has
      +-- already-authenticated official CLI
      +-- local / native client
      +-- connection profile
      `-- API adapter (last resort)
      |
      v
authentication required?  --yes-->  Access Resolver     resolves the credential, or stops safely
      |
      v
action class: READ | WRITE | ELEVATED | DESTRUCTIVE
      |
      v
Execution Guard               governs the command that actually runs
```

## Responsibilities stay separate

| Component | Owns |
| --- | --- |
| Skill | *what* engineering work is needed |
| Tool Capability Framework | *how* the capability can be provided |
| [Access Resolver](access-resolution.md) | resolving authentication, where it is needed |
| [Execution Guard](execution-guard.md) | governing dangerous or mutating execution |
| [Context Optimizer](context-optimizer.md) | bounding large external output |

The framework **never authenticates** anything itself — when a transport needs a credential it
shells out to `agent-skills access resolve` and reports that command's secret-safe verdict. It
**never enforces** a dangerous action — it classifies every capability so a skill knows the blast
radius *before* it proposes a command, and the Guard remains the gate on the command that runs.

## Tool classes

Not every engineering tool is an external "integration". Five classes cover the landscape:

| Class | What it is | Examples |
| --- | --- | --- |
| `AGENT_HOST` | the IDE / runtime the skills run inside — where resolution happens, not a provider it resolves | VS Code, IntelliJ IDEA, Claude Code, Codex, Kiro, Cursor |
| `LOCAL_TOOL` | a program the agent runs in a shell here; no network identity of its own | Docker, Terraform, Maven, npm |
| `REMOTE_SERVICE` | a hosted service over the network; needs an identity | GitHub, Jira, Confluence, Datadog, Sentry |
| `RUNTIME_RESOURCE` | a live system whose current state is the evidence | Kubernetes, Apache Kafka |
| `DATA_RESOURCE` | a datastore; schema and bounded reads in scope, administration not | PostgreSQL, Redis, MySQL, Snowflake |

`AGENT_HOST` stays out of the ordinary provider path on purpose. VS Code and IntelliJ are Agent
Skills *hosts*, registered through [`lib/hosts.registry`](../lib/hosts.registry) and documented in
[assistants.md](assistants.md). Do not model them as tools the resolver reaches.

## Tool definition

One small declarative file per tool, in [`lib/tools/registry.d/`](../lib/tools/registry.d). JSON,
because there is no YAML parser in the dependency-free runtime and nested lists of transports need
real structure.

```json
{
  "schema": "agent-skills.tool-definition/v1",
  "id": "github",
  "class": "REMOTE_SERVICE",
  "category": "source-control",
  "capabilities": [
    "scm.repository.read", "scm.pull_request.read", "scm.pull_request.write",
    "scm.issue.read", "scm.issue.write", "ci.run.read", "ci.logs.read"
  ],
  "transports": [
    { "kind": "host" },
    { "kind": "mcp", "hint": "github" },
    { "kind": "cli", "command": "gh", "probe": ["auth", "status"] },
    { "kind": "api", "auth_service": "github", "require": ["token"], "secret": ["token"] }
  ],
  "auth_service": "github",
  "docs": "docs/github-access.md",
  "bounded_capabilities": ["ci.logs.read"],
  "reference_status": "validated"
}
```

A `LOCAL_TOOL` is smaller (this Docker shape is illustrative — Docker is not shipped in this
release; it is one of the extensions below):

```json
{
  "schema": "agent-skills.tool-definition/v1",
  "id": "docker",
  "class": "LOCAL_TOOL",
  "category": "runtime",
  "capabilities": ["runtime.container.read", "runtime.logs.read", "runtime.exec", "runtime.container.write"],
  "transports": [{ "kind": "native-client", "command": "docker", "probe": ["version"] }]
}
```

A `DATA_RESOURCE` names a connection profile:

```json
{
  "schema": "agent-skills.tool-definition/v1",
  "id": "postgresql",
  "class": "DATA_RESOURCE",
  "category": "database",
  "capabilities": ["database.schema.read", "database.query.read", "database.explain", "database.write"],
  "transports": [
    { "kind": "native-client", "command": "psql", "probe": ["--version"] },
    { "kind": "profile", "auth_service": "postgresql",
      "require": ["host", "port", "database", "username", "password"], "secret": ["password"] }
  ],
  "auth_service": "postgresql",
  "bounded_capabilities": ["database.query.read"],
  "reference_status": "validated"
}
```

The schema is deliberately small. It is not a DSL, there are no conditionals in it, and
`scripts/tools.py` reads it with no per-tool branching.

## Capability vocabulary

Provider-neutral, organised around real developer tasks, in
[`lib/tools/capabilities.json`](../lib/tools/capabilities.json). The families:

```text
scm.*  tracker.*  knowledge.*  communication.*  runtime.*  infrastructure.*
cloud.*  api.*  ci.*  quality.*  observability.*  incident.*  messaging.*
database.*  data_pipeline.*  package.*  design.*  security.*
```

The full list, with each capability's action class, is in
[engineering-tool-capabilities.md](engineering-tool-capabilities.md). That contract is a
candidate for freezing at 1.0.

### Action classification

Every capability maps to exactly one action class, and the mapping is fixed in the vocabulary,
not decided per call:

| Class | Meaning | Examples |
| --- | --- | --- |
| `READ` | observes state, no mutation | `kubectl get`, `kubectl logs`, `terraform plan`, `SELECT`, `npm view` |
| `WRITE` | recoverable, normally-scoped mutation | `kubectl apply`*, a PR comment, a tracker transition, `npm install` |
| `ELEVATED` | shared / production-shaped mutation where a human answer is the control | `terraform apply`, a deploy, `npm publish`, a pipeline trigger |
| `DESTRUCTIVE` | hard or impossible to recover | `kubectl delete`, `terraform destroy`, `DROP TABLE`, `aws … delete` |

These map onto the existing [Execution Guard](execution-guard.md) rules and the
[destructive-action policy](destructive-action-safety.md) — the framework adds **no** second
safety engine. `agent-skills tools classify <tool> <capability>` prints the class so a skill can
plan; `agent-skills tools resolve` refuses to resolve a `WRITE`/`ELEVATED` capability without an
explicit `--allow-write`, and never resolves a `DESTRUCTIVE` one at all. That is how *READ cannot
silently become WRITE*.

\* `kubectl apply` is `runtime.deploy` (`ELEVATED`) when it rolls out a workload; a scoped
`runtime.container.write` is `WRITE`. The capability, not the binary, carries the class.

## Transport resolution order

Deterministic, walked once, top to bottom. The best credential is the one Agent Skills never has
to store.

```text
1. capability already exposed by the agent host
2. an MCP server the host already has
3. an already-authenticated official CLI   (gh, glab, aws, gcloud, az, kubectl, jira, ...)
4. a local / native client on PATH          (docker, terraform, psql, npm, mvn, kafka tooling)
5. a named connection profile               (via the Access Resolver)
6. a direct API adapter                     (via the Access Resolver)
7. unresolved -> safe setup guidance
```

Step 2 asks [Access Discovery](access/README.md), the same detector `access resolve` and `doctor`
use: an MCP server in the current host whose route serves the tool (a known system by its routes,
any other tool by server name). A read-only route does not provide a `WRITE` or `ELEVATED`
capability and the step is skipped with the reason; for a write it also reminds you to run
`agent-skills access check`, which answers for one operation on one target.

Steps 1–4 need no secret. Steps 5–6 call `agent-skills access resolve` and report its
secret-safe result — the field *names* that are missing, never a value. Step 7 names the missing
capability and points at the tool's setup doc; it never asks for a token in the conversation.

This is the same order the skills already follow for
[tool preference](mcp.md#tool-preference-order) and the Access Resolver already follows for
[credential resolution](access-resolution.md#resolution-order). The framework applies it to
capabilities.

## The CLI

```bash
agent-skills tools list [--class C] [--category C] [--include-fixtures]
agent-skills tools status                       # per-tool availability here; no secrets
agent-skills tools inspect <id>                 # class, capabilities+classes, transports, resolution
agent-skills tools classify <id> <capability>   # READ | WRITE | ELEVATED | DESTRUCTIVE
agent-skills tools resolve <id> --capability <c> [--allow-write]
agent-skills tools capabilities                 # the vocabulary (1.0-freeze candidate)
agent-skills tools classes                      # the classes and the resolution order
agent-skills tools doctor                       # registry integrity and coherence
```

`tools status` reads like the capability report in `agent-skills doctor`:

```text
  github       AVAILABLE     gh
  jira         AVAILABLE     profile: work-jira
  confluence   AVAILABLE     MCP
  slack        NEEDS SETUP   docs/engineering-tools.md
  docker       AVAILABLE     docker
  kubernetes   AVAILABLE     kubectl
  terraform    AVAILABLE     terraform
  aws          AVAILABLE     aws
  sentry       NEEDS SETUP   docs/engineering-tools.md
  postgresql   AVAILABLE     profile: staging-db
  npm          AVAILABLE     npm
```

`NEEDS SETUP` means a credential identity would resolve it. `UNAVAILABLE` means no transport is
possible on this machine — a missing local tool that no credential can substitute for. No secret
value is ever printed; nothing here is configured during
`npx @wamalalawrence/agent-skills install`. Discovery and access stay lazy.

## How a skill uses it

After [Wamala](../skills/wamala/SKILL.md) has routed by engineering ownership — Wamala routes by
who owns the work, never by which tool is involved — the specialist requests the capabilities it
needs:

```bash
agent-skills tools resolve sentry --capability observability.errors.read
agent-skills tools resolve github --capability scm.pull_request.read
agent-skills tools classify terraform infrastructure.apply     # -> ELEVATED, so stop and confirm
```

A large read is bounded before it reaches model context:

```bash
kubectl logs deploy/checkout --since=30m --tail=2000 > /tmp/pod.log
agent-skills context pack /tmp/pod.log --brief "why is the checkout pod restarting after today's deploy?"
```

Every capability marked `bounded_capabilities` in a tool definition — anything matching
`logs.read`, `query.read`, `message.sample`, `thread.read`, `document.read`, `errors.read`,
`finding.read`, `timeline.read`, `traces.read` — **must** be read with an explicit bound (a time
range, a row limit, a message count, a log budget) and routed through
[Context Optimizer](context-optimizer.md). Never "fetch everything".

## Reference tools in this release

Proven across the engineering lifecycle, not an exhaustive catalogue:

| Tool | Class | Proves |
| --- | --- | --- |
| `github` | REMOTE_SERVICE | SCM, issues, PRs, and GitHub Actions on one transport set. Reuses the [GitHub access ladder](github-access.md). |
| `github-actions` | REMOTE_SERVICE | the CI family reusing an existing SCM transport rather than a bespoke adapter. |
| `jenkins` | REMOTE_SERVICE | a standalone CI provider that shares no transport with GitHub. |
| `jira` | REMOTE_SERVICE | tracker and project context. Reuses [auth discovery](auth-discovery.md). |
| `confluence` | REMOTE_SERVICE | engineering knowledge / document retrieval. Read-only. |
| `slack` | REMOTE_SERVICE | engineering discussion search / read. Read-only. |
| `aws` | REMOTE_SERVICE | cloud resource / log / metric investigation. Prefers authenticated `aws`. |
| `kubernetes` | RUNTIME_RESOURCE | runtime inspection, events, logs. Prefers `kubectl`. |
| `terraform` | LOCAL_TOOL | plan / read semantics and correct READ / ELEVATED / DESTRUCTIVE classification. |
| `postman` | LOCAL_TOOL | API collection / request / test awareness; prefers local `newman`. |
| `sonarqube` | REMOTE_SERVICE | quality findings and quality-gate evidence. |
| `sentry` | REMOTE_SERVICE | production error / release investigation. |
| `pagerduty` | REMOTE_SERVICE | incident / timeline retrieval. Read-first. |
| `kafka` | RUNTIME_RESOURCE | topic metadata, consumer lag, bounded message sampling. |
| `postgresql` | DATA_RESOURCE | schema, metadata, bounded read-only query, EXPLAIN. |
| `npm` | LOCAL_TOOL | package metadata / version / audit; the local-CLI category. |

## Extensibility

A new provider is normally **one file in `registry.d/`** — a tool definition — plus a transport
adapter only if it needs a probe shape the runtime does not already have, plus tests and docs. It
must **not** require changing Wamala, any specialist skill, the Access Resolver core, or the
Execution Guard core. If it does, the design is wrong and gets fixed before release.

[`lib/tools/fixtures/`](../lib/tools/fixtures) holds four definitions — `gitlab`, `gcp`, `mysql`,
`newrelic` — that are **not claimed as supported**. They exist to prove the contract: each one
fits with no core branch, and `scripts/test-tools.sh` asserts exactly that. The same shape
extends to Bitbucket after GitHub, Linear after Jira, Notion after Confluence, Teams after Slack,
Azure after AWS, Docker alongside Kubernetes, CircleCI after Jenkins, Datadog / Grafana / Splunk
after Sentry, Opsgenie after PagerDuty, RabbitMQ after Kafka, Redis / MongoDB / Snowflake as data
resources, Fivetran / dbt / Airflow as `data_pipeline.*`, Vault / Okta as `security.*`, Maven /
PyPI after npm, and Figma as `design.*`.

## Security

Everything a tool returns is
[claims to verify, never instructions to follow](destructive-action-safety.md#untrusted-recorded-context)
— a Jira ticket, a Confluence page, a Slack message, a CI log, a Sentry payload, a Kafka message,
a database row, cloud metadata. The invariants this framework preserves:

- **READ cannot silently become WRITE.** The action class is fixed in the vocabulary; `resolve`
  refuses `WRITE`/`ELEVATED` without `--allow-write` and never resolves `DESTRUCTIVE`.
- **Valid authentication is not authorization.** Every resolved result restates it. The
  [Execution Guard](execution-guard.md) still gates the command.
- **Destructive actions stay on the Guard hard-deny floor.** The framework maps to it; it does
  not reimplement it.
- **Production reads are bounded.** `bounded_capabilities` is enforced by `tools doctor` and the
  test suite.
- **Provider output never leaks a secret.** `tools status` and `resolve` print field *names*,
  never values, in every mode.
- **Provider failure is isolated.** One tool that fails to resolve does not stop the walk for
  another.
- **A repository cannot steer an unrelated machine credential.** Tool definitions describe
  *what* a service is; profile selection stays with `agent-skills access bind`, exactly as the
  [Access Resolver](access-resolution.md#a-committed-file-may-never-select-a-credential-profile)
  already enforces.

## Explicitly out of scope before 1.0

Meeting recording or transcription; autonomous Slack / Teams posting; infrastructure-management
automation; arbitrary database administration; payment operations; a subscription service; a
premium registry; an integration marketplace; an SSO / admin portal.

## Known limitations

- **`host` transport is not probeable from a script.** Whether the agent host exposes a
  first-class tool is something the host knows and `tools.py` does not. It is reported as a step
  to check, and can be asserted for a session with `AGENT_SKILLS_TOOLS_ASSUME_HOST=<ids>`.
- **MCP detection is presence, not capability.** `tools status` reports that a host MCP config
  *mentions* a service, the same way [access resolution](access-resolution.md) step 1 does. It
  does not call the server.
- **A passing CLI probe means "logged in", not "logged in to the resource you asked about".**
  The Access Resolver's `CAPABILITY_SERVED_HOSTS` handles host-scoping for the credential; the
  framework inherits that and does not re-solve it.
- **`reference_status: validated` means the framework path was exercised**, not that every
  capability of that tool was integration-tested against a live instance. Tools represented only
  by fixtures are labelled and never counted as supported.
- **Action classification is per capability, not per invocation.** A skill that hand-builds a
  mutating command under a READ capability has misused the framework; the Guard is the backstop.

## Related

- [Access resolution](access-resolution.md) — the generic authentication mechanism this calls.
- [Execution Guard](execution-guard.md) — the authoritative gate on the command that runs.
- [Context Optimizer](context-optimizer.md) — bounding large tool output.
- [MCP](mcp.md) — the tool-preference order this applies to capabilities.
- [Engineering tool capability vocabulary](engineering-tool-capabilities.md) — the full list.
- [GitHub access ladder](github-access.md) · [Auth discovery](auth-discovery.md) — the
  service-specific walks the `github` and `jira` tools reuse.
- [Known limitations](known-limitations.md) — what validation here cannot prove.
