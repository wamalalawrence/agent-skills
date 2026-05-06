# Eval: Jira Issue Scope And Existing PR Detection

**Skills under test:** `software-engineer`, `issue-investigator`, `code-reviewer`.

**Targeted failure modes:**

- The agent combines two independent Jira tasks into one implementation branch and one PR.
- The agent starts a new branch for a Jira ticket that already has an open PR or remote branch
  likely addressing the same issue.

## Workspace fixture

```text
<workspace>/
  .env                         # PROJECTS_JSON maps example-api, GITHUB_DEFAULT_BRANCH=main
  example-api/                  # git repo with origin configured
    README.md
    CONTRIBUTING.md
```

The GitHub remote has:

- Open PR `#42`, title `PROJ-123 redirect expired SAML sessions`, branch
  `bugfix/PROJ-123-saml-expiry-redirect`.
- No PR for `PROJ-456`.

## Run script

1. User asks:
   *"Fix PROJ-123 and PROJ-456 in example-api."*
2. In a separate run, user asks:
   *"Fix PROJ-123 in example-api."*

## Expected agent behavior

- For the first run, `software-engineer` stops before branch creation and reports that two
  independent Jira tasks must be split. It may offer an execution order, but it must not make one
  branch or PR for both keys.
- For the second run, `software-engineer` / `issue-investigator` checks open PRs and remote
  branches before creating a new branch. With GitHub available, it uses a search equivalent to
  `gh pr list --state open --search "PROJ-123 in:title,body,comments"` and a remote-branch check.
- The agent persists the finding under `evidence-pack.yml.related_work` with
  `already_addressed_status: possible | likely | confirmed`.
- If PR `#42` appears to cover the same root cause or acceptance criteria, the agent calls it out
  and asks whether to review/continue that PR or supersede it. It does not create a competing
  branch silently.
- `code-reviewer` surfaces a `blocker` if asked to approve a PR that bundles `PROJ-123` and
  `PROJ-456` as independent implementation scope.

## Must Not Do

- Must not use a branch name containing two Jira keys to justify bundling both tasks.
- Must not bury the existing PR as a low-priority note after starting a new implementation.
- Must not treat linked parent, duplicate, or related tickets as implementation scope unless the
  user explicitly made one of them the primary Jira task for that branch.

## Pass / Fail Checklist

- [ ] One primary Jira task maps to one branch and one PR.
- [ ] Multiple independent Jira keys stop implementation before branch creation.
- [ ] Open PRs and remote branches for the primary key are checked before creating a branch.
- [ ] Likely existing work is surfaced as a decision point, not overwritten.
- [ ] Bundled independent Jira keys are a code-review blocker.
