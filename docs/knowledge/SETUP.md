# Setting up a shared knowledge source

Two roles. A **source admin** creates and protects the source once per isolation boundary,
usually one per organisation or legal entity. A consultant working for two clients has two
sources, and nothing flows between them. An **engineer** connects to the source through
discovery.

`agent-skills doctor` reports which setup steps are verifiably missing: no manifest, no
CODEOWNERS, no CI running `knowledge check`, and no pointer file in a bound repository.

## Source admin

### 1. Check that there is not one already

Two sources for one organisation is how knowledge diverges again. `init-source` checks for you,
and refuses when:

- a source you have configured already serves `--org`;
- `engineering-knowledge` beside the new repository (same host, same org) already has an active
  manifest for that org;
- the directory, or its remote, already contains a manifest.

`--force --reason "<why>"` overrides the first two, and the reason is recorded in the new
manifest as `created_despite_existing_source`.

### 2. Create the repository and scaffold it

Create an **empty** repository on your git host (GitHub, GitLab, Azure DevOps, Bitbucket, or
self-hosted), preferably named `engineering-knowledge` so discovery finds it. Then:

```bash
git clone git@example.com:acme/engineering-knowledge.git
agent-skills knowledge init-source engineering-knowledge --org acme
```

This writes, and does not commit:

| File | Purpose |
| --- | --- |
| `.agent-skills-knowledge.json` | manifest: `source_id` (UUID), `org`, `schema_version`, `status`, `allowed_scopes`, `policy` |
| `CODEOWNERS` | reviewers per scope directory; adapt the team handles |
| `README.md` | how the repository is used and how to review a proposal |
| `.github/workflows/knowledge-check.yml` | CI template; adapt the install step (other CI systems run the same command) |
| `facts/{organization,team,project,repository}/` | one JSON file per fact, by scope |

Options: `--scope <pattern>` (repeatable) narrows `allowed_scopes` (the default is
`organization:<org>`, `team:*`, `project:*`, `repository:*`), and `--names-policy
action_owners_only|none|allowed` sets whether person names may appear in shared facts. The
default allows names only as ACTION owners.

Review the scaffold, commit it, and push it to the default branch.

### 3. Protect the default branch

On your host, for the default branch:

- require a pull or merge request, and at least one approving review;
- require review from code owners;
- make the `knowledge-check` job a required status check;
- optionally require signed commits.

Agent Skills relies on this and does not reimplement it. The client never pushes to the default
branch, but other clients and people can, and branch protection is what makes "merged" mean
"reviewed". A file that lands without a merge is shown to readers as PROPOSED, never CONFIRMED.

Prefer merge commits, or your host's squash/rebase merge (recognised by the host committer and
the PR number in the subject). Approval provenance is read from them.

### 4. Point code repositories at it

In each code repository of the organisation:

```bash
agent-skills knowledge sources bind acme --write-pointer
git add .agent-skills/knowledge.json && git commit -m "Point agents at the engineering knowledge source"
```

The pointer is how engineers get the source offered with an ordinary confirmation.

### 5. Optional policy

- **Verification-only PRs.** A proposal that only refreshes `last_verified_at` / `verification`,
  or marks a fact STALE, is low risk. Your CI may auto-merge those. That is your policy decision,
  not Agent Skills'.
- **Retiring a source.** To merge a duplicate source into this one, an engineer bound here runs
  `agent-skills knowledge propose --from-source <old>`. Ids that already exist become
  corroborations, and provenance is kept in `imported_from`. After that merges, set the old
  manifest's `status` to `deprecated` and `successor` to this URL. Clients reading it are told to
  switch, and can no longer propose to it.

## Engineer

From any repository of the organisation:

```bash
agent-skills knowledge sources add          # discovery: pointer file, then the well-known name
agent-skills knowledge status
```

Then work normally. `start-task` shows shared facts, and your agent may suggest proposing what
you learned. You decide.

Leaving: `agent-skills knowledge sources remove <name>` deletes the local clone, index, outbox,
proposal records, and bindings for that source, after confirmation.
