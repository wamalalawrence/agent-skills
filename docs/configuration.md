# Configuration

Most repositories need none.

`agent-skills` derives what it can from the repository itself, so configuration is something you add
when inference is not good enough — not a precondition for using the skills. Credentials are a
separate concern entirely and never appear in any file described here; see
[access-resolution.md](access-resolution.md).

## What is inferred, with no configuration at all

```bash
agent-skills project
agent-skills project --json
agent-skills project --field build
```

| Value | Derived from |
| --- | --- |
| repository root, name, slug | `git rev-parse`, directory name |
| remote, `owner/name` | `remote.origin.url` |
| current branch | `git rev-parse --abbrev-ref HEAD` |
| base branch | `origin/HEAD`, then a conventional `origin/<main\|master\|develop\|trunk>`, then a local branch |
| stack and build system | `pom.xml`, `build.gradle`, `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, `composer.json`, `mix.exs`, `global.json` |
| package manager | `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`, `package-lock.json` |
| build and format commands | the scripts and tool configuration that actually exist in the repo |
| CI | `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, and similar |
| repo knowledge base | `<repo>/.agent-skills/knowledge/` |
| vendored skills | `<repo>/.agent-skills/skills/` |

Every field reports **where it came from**, and anything that could not be established safely lands
in `needs_confirmation` rather than being asserted:

```text
confirm before relying on:
  - build command 'mvn clean verify' is inferred from the build system, not read from this
    repository. Confirm it before treating a run as authoritative.
```

That distinction is the point. An inferred `pytest` for a repository with no tests is a command that
fails for reasons unrelated to the change under review, so the skills are told to confirm it rather
than trust it.

Node and Python commands are built only from scripts and tool configuration that exist. A repository
with no `test` script gets no test command, and the gap is reported instead of filled with a guess.

## When to add committed configuration

Add `.agent-skills.yml` at the repository root when:

- the real build or format command is not derivable (a wrapper script, an unusual profile, a
  monorepo target);
- the base branch is not conventional;
- the display name should differ from the directory name;
- a coverage target or runtime version applies to this repository;
- the repository runs in cloud agents and needs `mode: in-repo`;
- you want to pin a skill source with `skills.canonical_dir`.

Copy [`.agent-skills.example.yml`](../.agent-skills.example.yml), fill in what matters, delete the
rest, and commit it. Committed values win over inference, because a human wrote them.

```yaml
project:
  name: "example-api"
  stack: "java"
  base_branch: "develop"
  build: "mvn -Pintegration clean verify"
  format: "mvn fmt:format && mvn fmt:check"
  runtime_version: "21"
  coverage_target: "85"
```

### `.agent-skills.yml` is secret-free, and that is enforced

It is committed, so from the resolver's point of view it is attacker-controlled: anyone who can open
a pull request can edit it. Two consequences, both binding:

- **No credential values.** Ever.
- **No credential profile names.** A committed file may declare *what* a service is (a name, a host);
  it may not select *which* identity to unlock. Profile selection comes only from the user-global
  binding registry or an untracked `.agent-skills.local.yml`, and untrackedness is verified with git
  rather than inferred from the filename.

So a repository cannot contain "use `production-readonly-db`" and thereby reach a credential that
has nothing to do with it. See
[access-resolution.md](access-resolution.md#security-boundaries).

## Project-local overrides that are not committed

For values that belong to your checkout rather than the project, use a gitignored
`.agent-skills.local.yml`:

```yaml
# .agent-skills.local.yml — add to .gitignore
credentials:
  jira: work-jira
  github: work-github

jira:
  host: "https://sandbox.example.atlassian.net"
```

Add it to `.gitignore` before you create it. If git tracks it, the resolver ignores the **whole
file** — not just its `credentials:` block — and says why. The `jira.host` above would be dropped
too. That is the enforcement point described earlier, not an inconvenience: once the file is
committed, nothing in it is distinguishable from anything else a pull request could add.

The same rule covers a legacy `.env`, `.env.local`, or `.jira-config.yml` **inside** the repository.
Those files outside the repository, such as in the legacy workspace folder above it, are unaffected.

If git cannot answer whether the file is tracked — git not installed, or refusing to read the
repository — the file is refused rather than trusted. "Provably untracked" is the condition, and an
unanswerable question is not a yes.

Within step 4 of the [resolution order](access-resolution.md#resolution-order), an untracked
`.agent-skills.local.yml` takes precedence over `agent-skills access bind`: the file is closer to
your checkout, so it wins for that one repository. Delete the `credentials:` entry if you want the
global binding to apply.

An equivalent, and often better, alternative keeps the repository completely clean:

```bash
agent-skills access bind --service jira --profile work-jira
```

That writes to a user-global registry keyed by the repository's git remote, so it survives the repo
being moved or re-cloned and adds no file to the tree.

## Top-level keys

| Key | Required | Notes |
| --- | --- | --- |
| `mode` | for cloud agents | `in-repo`. Omit for local work. |
| `org_name` | no | Display name in summaries and PR text. |
| `org_domain` | no | Identity domain for written output. |
| `github_org` | for clone/push/PR work | GitHub owner. Usually inferable from the remote. |
| `github_default_branch` | no | Falls back to the detected base branch. |
| `project` | no | Overrides inference for this repository. |
| `jira.host`, `jira.default_project_key` | for tracker work | Host metadata only. The credential is never here. |
| `confluence.host` | for doc lookups | Host metadata only. |
| `cache_dir` | no | Overrides `<repo>/.cache/agent-skills/`. Same as `AGENT_SKILLS_CACHE_DIR`. |
| `writing.ai_attribution` | no | `none` \| `trailer` \| `footer`. See [writing voice](writing-voice.md). |
| `writing.voice_reference` | no | Path to a local writing sample to match. |
| `skills.canonical_dir` | no | Pin the skill source. See [skill-source resolution](skill-source-resolution.md). |
| `context_optimizer.*` | no | Large-input bounds. See below and [Context Optimizer](context-optimizer.md). |

## Context Optimizer bounds

Past the large-input threshold a skill builds a bounded context pack instead of reading a file
whole. The defaults were measured against a real repository rather than picked for roundness, but a
codebase of 300-line services and a monorepo of generated clients will reasonably disagree — so all
five bounds are configurable.

| Key | Default | What it bounds |
| --- | --- | --- |
| `context_optimizer.threshold_chars` | `65536` | Characters past which an input needs a pack. |
| `context_optimizer.threshold_lines` | `2000` | Lines past which an input needs a pack. |
| `context_optimizer.budget_chars` | `10000` | Default size of a pack, provenance included. |
| `context_optimizer.relation_depth` | `1` | How far structural relations (foreign keys) are followed. |
| `context_optimizer.max_read_bytes` | `67108864` | Whole-file read cap for structure-bearing formats. |

Precedence is `CLI flag` > environment variable > committed `.agent-skills.yml` > default. The
environment variable is the key upper-cased with an `AGENT_SKILLS_CONTEXT_` prefix, so
`AGENT_SKILLS_CONTEXT_BUDGET_CHARS=25000` raises the default budget for one session.

Every override is echoed on stderr, so a surprising threshold is visible rather than mysterious:

```text
-- limit: .agent-skills.yml set threshold_chars to 20000
```

The scope is deliberately narrow. A committed file may adjust a **resource bound** and nothing
else: it cannot name a path, a credential, a strategy, or a tool policy. Values outside a sane range
are clamped rather than obeyed, and a non-numeric value falls back to the default with a note —
because a committed file is editable by anyone who can open a pull request, which is the same
reasoning as [access resolution](access-resolution.md).

## Cache path

```text
${AGENT_SKILLS_CACHE_DIR:-<repo-root>/.cache/agent-skills/<issue-key>/}
```

Evidence packs, repro recipes, definition-of-done artifacts, project memory, the blackboard, and
telemetry live here. The repository root is found with `git rev-parse --show-toplevel`, so running a
skill from a nested directory does not create a second cache.

Add `.cache/` to the repository's `.gitignore`. In legacy workspace mode the cache is
`${WORKSPACE_ROOT}/.cache/agent-skills/`; add the ignore rule there yourself.

## Legacy workspace configuration

Installs from v0.36.x and earlier keep a `${WORKSPACE_ROOT}/.env` with a managed marker block
(`ORG_NAME`, `WORKSPACE_ROOT`, `PROJECTS_JSON`, `JIRA_*`, `CONFLUENCE_*`, `SONAR_*`,
`ENVIRONMENTS_JSON`). That file still works:

- the access resolver discovers it and maps the long-standing variable names onto fields;
- nothing writes or rewrites it any more. v0.43.0 removed the code that did, so the file is yours
  alone and no installer will touch, normalise, or clear it.

`PROJECTS_JSON` is no longer needed for a repository to be understood — inference covers it — but it
is still read where present. The annotated schema lives in [`.env.example`](../.env.example), which
is now a legacy reference rather than the primary configuration surface.

Migration: [installation.md](installation.md#coming-from-the-pre-v037-workspace-layout), or run
`agent-skills migrate`.

### The marker block (legacy)

An `.env` written before v0.43.0 carries a managed block:

```text
# >>> agent-skills setup.init
... managed keys ...
# <<< agent-skills setup.init
```

It is now inert punctuation. Nothing rewrites the block, so edits inside and outside it are equally
safe. One rule survives because shell sourcing still applies: never define the same key twice, since
the last assignment silently wins. `scripts/validate-repo.py` fails on that.

## Related

- [Access resolution](access-resolution.md) — credentials, which are not configuration.
- [Installation](installation.md) — the global install and the migration path.
- [Execution modes](execution-modes.md) — which configuration applies where.
- [Skill-source resolution](skill-source-resolution.md) — the `skills:` block.
- [`.agent-skills.example.yml`](../.agent-skills.example.yml) — the annotated template.
