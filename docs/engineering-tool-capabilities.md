# Engineering Tool Capability Vocabulary

The provider-neutral vocabulary a skill uses to ask the
[Engineering Tool Capability Framework](engineering-tools.md) for what it needs. It describes
**engineering work**, not vendor features. `git`, `hg`, GitHub, GitLab and Bitbucket all provide
`scm.pull_request.read`; the skill asks for that, and the framework picks the transport.

The machine-readable source is [`lib/tools/capabilities.json`](../lib/tools/capabilities.json).
This page and that file must agree — `scripts/test-tools.sh` asserts it.

## Status for 1.0

This contract is a **candidate for freezing at `1.0.0`**. After the freeze:

- adding a capability is a compatible (minor) change;
- renaming a capability, or moving one to a different action class, is a breaking (major) change;
- the eighteen family prefixes are the stable extension points.

Until then, treat the names as stable-in-practice but not yet guaranteed. Pin the release when
you automate against them.

## Action classes

Every capability maps to exactly one, fixed in the vocabulary rather than decided per call:

| Class | Meaning |
| --- | --- |
| `READ` | Observes state. No mutation. Still subject to the bounded-output rule for large reads. |
| `WRITE` | Recoverable, normally-scoped mutation — a comment, an issue, a branch, a predicated row, a local install. |
| `ELEVATED` | Shared or production-shaped mutation where a human answer is the right control — an infra apply, a deploy, a publish, a pipeline trigger. |
| `DESTRUCTIVE` | Removes or overwrites state that is hard or impossible to recover. Governed by the [Execution Guard](execution-guard.md) hard-deny floor. |

Ordering: `READ` < `WRITE` < `ELEVATED` < `DESTRUCTIVE`. `agent-skills tools classify <tool>
<capability>` prints the class. `agent-skills tools resolve` will not resolve a transport for a
`WRITE`/`ELEVATED` capability without `--allow-write`, and never for a `DESTRUCTIVE` one.

Names whose suffix fixes the class — asserted by `tools doctor`:

| Suffix | Forced class |
| --- | --- |
| `.plan`, `.explain` | `READ` |
| `.apply`, `.publish`, `.trigger`, `.deploy` | `ELEVATED` |
| `.destroy`, `.delete` | `DESTRUCTIVE` |

## Bounded reads

A capability whose name contains `logs.read`, `query.read`, `message.sample`, `thread.read`,
`document.read`, `errors.read`, `finding.read`, `timeline.read`, or `traces.read` returns a
potentially huge, potentially hostile external payload. Every tool that owns one lists it under
`bounded_capabilities`, and the consuming skill **must** read it with an explicit bound and route
it through [Context Optimizer](context-optimizer.md). Never "fetch everything".

## The vocabulary

### `scm.*` — source control

| Capability | Class | Summary |
| --- | --- | --- |
| `scm.repository.read` | `READ` | Read repository metadata, branches, files, commits. |
| `scm.pull_request.read` | `READ` | Read pull/merge request state, diffs, reviews, checks. |
| `scm.pull_request.write` | `WRITE` | Open, comment on, or update a pull/merge request. |
| `scm.issue.read` | `READ` | Read issues and their comments. |
| `scm.issue.write` | `WRITE` | Open, comment on, or transition an issue. |
| `scm.branch.write` | `WRITE` | Create or update a branch or ref. |
| `scm.release.read` | `READ` | Read releases and tags. |

### `tracker.*` — planning / issue tracking

| Capability | Class | Summary |
| --- | --- | --- |
| `tracker.issue.read` | `READ` | Read a tracker ticket: summary, description, status, links. |
| `tracker.issue.write` | `WRITE` | Create, comment on, or transition a tracker ticket. |
| `tracker.project.read` | `READ` | Read project, board, backlog, and sprint context. |

### `knowledge.*` — engineering knowledge base

| Capability | Class | Summary |
| --- | --- | --- |
| `knowledge.search` | `READ` | Search an engineering knowledge base. |
| `knowledge.document.read` | `READ` | Read a knowledge document or page. |
| `knowledge.document.write` | `WRITE` | Create or update a knowledge document. |

### `communication.*` — team chat

| Capability | Class | Summary |
| --- | --- | --- |
| `communication.search` | `READ` | Search messages across channels. |
| `communication.thread.read` | `READ` | Read a message thread. |
| `communication.message.write` | `WRITE` | Post a message. Not enabled for any reference tool in this release. |

### `runtime.*` — live workloads / containers

| Capability | Class | Summary |
| --- | --- | --- |
| `runtime.workload.read` | `READ` | Read workload / container / pod state. |
| `runtime.container.read` | `READ` | List and inspect containers. |
| `runtime.logs.read` | `READ` | Read runtime logs. Bounded output. |
| `runtime.events.read` | `READ` | Read runtime events. |
| `runtime.exec` | `WRITE` | Execute a command inside a running workload. |
| `runtime.container.write` | `WRITE` | Start, stop, or update a container. |
| `runtime.deploy` | `ELEVATED` | Apply a workload change / roll out a deployment. |
| `runtime.workload.delete` | `DESTRUCTIVE` | Delete a workload, namespace, or node. |

### `infrastructure.*` — infrastructure as code

| Capability | Class | Summary |
| --- | --- | --- |
| `infrastructure.state.read` | `READ` | Read infrastructure state and outputs. |
| `infrastructure.plan` | `READ` | Produce a plan / preview of an infrastructure change. Does not mutate. |
| `infrastructure.apply` | `ELEVATED` | Apply an infrastructure change. |
| `infrastructure.destroy` | `DESTRUCTIVE` | Destroy infrastructure or remove resources from state. |

### `cloud.*` — cloud provider

| Capability | Class | Summary |
| --- | --- | --- |
| `cloud.resource.read` | `READ` | Describe cloud resources. |
| `cloud.logs.read` | `READ` | Read cloud logs. Bounded output. |
| `cloud.metrics.read` | `READ` | Read cloud metrics. |
| `cloud.resource.write` | `ELEVATED` | Create or update a cloud resource. |
| `cloud.resource.delete` | `DESTRUCTIVE` | Delete or terminate a cloud resource. |

### `api.*` — API development

| Capability | Class | Summary |
| --- | --- | --- |
| `api.collection.read` | `READ` | Read an API collection and its requests. |
| `api.request.read` | `READ` | Read a single API request definition. |
| `api.test.run` | `WRITE` | Run an API collection / contract test. Side effects depend on the target. |

### `ci.*` — CI / CD

| Capability | Class | Summary |
| --- | --- | --- |
| `ci.run.read` | `READ` | Read CI run status and history. |
| `ci.logs.read` | `READ` | Read CI job logs. Bounded output. |
| `ci.artifact.read` | `READ` | Read CI build artifacts and reports. |
| `ci.run.trigger` | `ELEVATED` | Trigger or re-run a pipeline. |

### `quality.*` — code quality

| Capability | Class | Summary |
| --- | --- | --- |
| `quality.finding.read` | `READ` | Read static-analysis findings / issues. |
| `quality.gate.read` | `READ` | Read quality-gate status for a project or branch. |
| `quality.coverage.read` | `READ` | Read coverage metrics. |

### `observability.*` — logs, metrics, traces, errors

| Capability | Class | Summary |
| --- | --- | --- |
| `observability.logs.read` | `READ` | Query logs. Bounded output. |
| `observability.metrics.read` | `READ` | Query metrics / time series. |
| `observability.traces.read` | `READ` | Read distributed traces. |
| `observability.errors.read` | `READ` | Read error / exception groups and their releases. |
| `observability.dashboard.read` | `READ` | Read a dashboard definition. |

### `incident.*` — incident management

| Capability | Class | Summary |
| --- | --- | --- |
| `incident.read` | `READ` | Read incident state and metadata. |
| `incident.timeline.read` | `READ` | Read an incident timeline / log of events. |
| `incident.write` | `WRITE` | Acknowledge, note, or update an incident. |

### `messaging.*` — brokers / queues

| Capability | Class | Summary |
| --- | --- | --- |
| `messaging.metadata.read` | `READ` | Read topic / queue / partition metadata. |
| `messaging.consumer_lag.read` | `READ` | Read consumer-group lag. |
| `messaging.message.sample` | `READ` | Read a bounded sample of messages. Bounded output; never a full drain. |

### `database.*` — data stores

| Capability | Class | Summary |
| --- | --- | --- |
| `database.schema.read` | `READ` | Read schema: tables, columns, indexes, constraints. |
| `database.metadata.read` | `READ` | Read catalog metadata, sizes, row estimates, activity. |
| `database.query.read` | `READ` | Run a bounded read-only query (SELECT). Row-limited. |
| `database.explain` | `READ` | Run EXPLAIN / EXPLAIN ANALYZE without side effects. |
| `database.write` | `WRITE` | Run a mutating statement with a predicate. DROP / TRUNCATE / unqualified DELETE remain on the Guard hard-deny floor. |

### `data_pipeline.*` — data engineering

| Capability | Class | Summary |
| --- | --- | --- |
| `data_pipeline.run.read` | `READ` | Read pipeline / DAG / sync run status. |
| `data_pipeline.logs.read` | `READ` | Read pipeline run logs. Bounded output. |
| `data_pipeline.model.read` | `READ` | Read model / transformation definitions and lineage. |
| `data_pipeline.trigger` | `ELEVATED` | Trigger a pipeline / sync / DAG run. |

### `package.*` — package ecosystems

| Capability | Class | Summary |
| --- | --- | --- |
| `package.metadata.read` | `READ` | Read package metadata, versions, dependents. |
| `package.audit` | `READ` | Run a dependency vulnerability audit. |
| `package.install` | `WRITE` | Install dependencies into the local project. |
| `package.publish` | `ELEVATED` | Publish a package to a registry. |

### `design.*` — design as engineering evidence

| Capability | Class | Summary |
| --- | --- | --- |
| `design.read` | `READ` | Read a design file / frame as engineering evidence. |
| `design.component.read` | `READ` | Read component / token specs from a design source. |

### `security.*` — secrets / identity

| Capability | Class | Summary |
| --- | --- | --- |
| `security.secret.read` | `READ` | Resolve a secret reference through a broker. The value never enters agent context — see the [Access Resolver](access-resolution.md). |
| `security.identity.read` | `READ` | Read identity / group / assignment metadata. |
| `security.policy.read` | `READ` | Read access policies and their bindings. |

## Related

- [Engineering Tool Capability Framework](engineering-tools.md) — how a capability is resolved.
- [Execution Guard](execution-guard.md) — the enforcement the action classes map onto.
- [Context Optimizer](context-optimizer.md) — the bounded-read requirement.
- [Access resolution](access-resolution.md) — the authentication step behind `profile` and `api`.
- [Versioning](versioning.md) — what "candidate for freezing at 1.0" commits to.
