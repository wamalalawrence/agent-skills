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

Add it to `.gitignore` before you create it. If git tracks it, the resolver ignores its
`credentials:` block and says why — that is the enforcement point above, not an inconvenience.

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

## Cache path

```text
${AGENT_SKILLS_CACHE_DIR:-<repo-root>/.cache/agent-skills/<issue-key>/}
```

Evidence packs, repro recipes, definition-of-done artifacts, project memory, the blackboard, and
telemetry live here. The repository root is found with `git rev-parse --show-toplevel`, so running a
skill from a nested directory does not create a second cache.

Add `.cache/` to the repository's `.gitignore`. In legacy workspace mode the cache is
`${WORKSPACE_ROOT}/.cache/agent-skills/` and `setup.init --legacy-workspace` writes the ignore rule
for you.

## Legacy workspace configuration

Installs from v0.36.x and earlier keep a `${WORKSPACE_ROOT}/.env` with a managed marker block
(`ORG_NAME`, `WORKSPACE_ROOT`, `PROJECTS_JSON`, `JIRA_*`, `CONFLUENCE_*`, `SONAR_*`,
`ENVIRONMENTS_JSON`). That file still works:

- the access resolver discovers it and maps the long-standing variable names onto fields;
- `./setup.init --legacy-workspace` still writes and refreshes it;
- `./setup.init --update` with an inherited `WORKSPACE_ROOT` preserves every value in it.

`PROJECTS_JSON` is no longer needed for a repository to be understood — inference covers it — but it
is still read where present. The annotated schema lives in [`.env.example`](../.env.example), which
is now a legacy reference rather than the primary configuration surface.

Migration: [installation.md](installation.md#upgrading-from-v036x-workspace-installation), or run
`agent-skills migrate`.

## Setup-managed marker block (legacy)

`setup.init --legacy-workspace` owns one block in `.env`:

```text
# >>> agent-skills setup.init
... managed keys ...
# <<< agent-skills setup.init
```

The block is overwritten on every rerun; edits **outside** it are preserved verbatim. Never define a
managed key a second time outside the block — shell sourcing means last assignment wins, so a
duplicate becomes a silent override. Both `setup.init --verify` and `scripts/validate-repo.py` fail
on that.

## Related

- [Access resolution](access-resolution.md) — credentials, which are not configuration.
- [Installation](installation.md) — the global install and the migration path.
- [Execution modes](execution-modes.md) — which configuration applies where.
- [Skill-source resolution](skill-source-resolution.md) — the `skills:` block.
- [`.agent-skills.example.yml`](../.agent-skills.example.yml) — the annotated template.
