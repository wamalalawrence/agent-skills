# GitHub access ladder

This page is the canonical reference an agent should follow when it needs to clone, fetch, push,
or open a PR against GitHub. The goal is the same as [auth-discovery](auth-discovery.md): an
agent should not say "I don't have access to GitHub" until it has walked the documented ladder.
The most common cause of a false dead-end is **the wrong active GitHub account on a machine that
has several** — switching accounts often resolves it without any new credentials.

## TL;DR for agents

1. Run `scripts/github-access.sh <owner>/<repo>`. It walks every step below in order and prints
   machine-greppable lines (`step1: ok`, `step3: gh repo view failed`, `suggest: gh auth switch
   …`). Read the suggestion line — do **not** stop at the first failed step.
2. If the script suggests `gh auth switch -h github.com -u <login>`, switch and re-run. On many
   developer laptops this is the actual fix.
3. Only after the script exits non-zero **and** every printed `suggest:` line has been tried may
   the agent surface "no GitHub access" to the user. The surface message must include which
   accounts are configured and which `<owner>/<repo>` was probed — never the active token.

## The ladder

Each step is independent. The first one that confirms access wins; later steps are only tried
when earlier ones fail.

1. **`gh auth status`** — does the local `gh` CLI have any account at all? When `gh` is not
   installed at all, skip to step 4.
2. **List logged-in accounts.** `gh` supports multiple accounts per host. The script prints
   `step2: active=<login>` and, when other accounts exist, `step2: other-accounts=<list>`. If
   the active account is not the one that owns the target repo's org, the next step will fail
   with a 404 — which looks like "no access" but is really "wrong account".
3. **Probe the target repo with `gh repo view <owner>/<repo>`.** This is the test that catches
   "active account can't see this org" — the most common false-dead-end. When this fails and
   another account is configured, the script suggests `gh auth switch -h github.com -u <other>`.
4. **HTTPS via git directly** — `git ls-remote https://github.com/<owner>/<repo>.git`. This
   uses git's own credential helpers (osxkeychain, libsecret, manager-core) and `~/.netrc`,
   which `gh` does not see. A team with a personal access token in the keychain often passes
   here even when `gh` does not.
5. **SSH** — `git ls-remote git@github.com:<owner>/<repo>.git`. Works when an SSH key is
   loaded for the right account; fails when the user has only configured HTTPS or vice versa.

## Common failure modes and what they really mean

| Symptom | Real cause | Fix |
| --- | --- | --- |
| `step3: gh repo view failed` with a 404 | Active gh account is wrong for this org | `gh auth switch -h github.com -u <other-login>` and re-run |
| `step3` 404 and only one account is configured | Active account genuinely has no access | Ask the user which login owns the org; `gh auth login -h github.com` for that login |
| `step1: not-logged-in` | gh installed but never logged in | `gh auth login -h github.com -p https -w` |
| `step4: https failed` after `step3: ok` | `gh` works but raw git doesn't (no credential helper) | Either rely on `gh` for clone/PR work, or run `gh auth setup-git` |
| `step5: ssh failed` after `step4: ok` | No SSH key for this account | HTTPS path is fine; do not insist on SSH |
| `gh CLI not installed` and HTTPS fails | Truly no path | Install `gh` (`brew install gh` / `apt install gh`) or set up a credential helper before retrying |

## Account switching is **not** a credential request

Switching the active `gh` account uses credentials that are already stored on the user's
machine. The agent does not need a new token from the user, does not see token values, and
does not write any secret to disk during the switch. Asking the user "which of these two logged-in
accounts owns `${GITHUB_ORG}`?" is allowed and encouraged; asking them for a token is reserved
for when no account is logged in at all.

## What an agent must report when the ladder is exhausted

> GitHub access not available for `${OWNER}/${REPO}`.
>
> - `gh` accounts on github.com: alice (active), bob.
> - `step3` (gh repo view) failed: 404. Tried `gh auth switch -h github.com -u bob` (suggested
>   automatically); `step3` still 404.
> - `step4` (git HTTPS) failed: authentication required.
> - `step5` (git SSH) failed: permission denied.
>
> Likely cause: neither logged-in GitHub account has access to the org `${OWNER}`. Please
> confirm the org name and which login should own this repo.

That message tells the user exactly what was tried, distinguishes "wrong account" from "no
account", and asks the smallest possible question.

## Cross-references

- [Auth discovery](auth-discovery.md) — Jira / Confluence equivalent ladder.
- [`scripts/github-access.sh`](../scripts/github-access.sh) — implementation.
- [Software-engineer SKILL.md, Phase 1.3](../skills/software-engineer/SKILL.md) — when the
  ladder is binding.
- [Project memory](project-memory.md) — record the verified per-project GitHub account
  preference once confirmed.
