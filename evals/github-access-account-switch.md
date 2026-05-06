# GitHub Access Eval: Two Logged-In Accounts, Wrong One Active

## Input Context

The user's laptop has `gh` 2.x installed and **two** GitHub accounts logged in for
`github.com`:

- `alice-personal` (active)
- `alice-work` (the one with access to the org `${GITHUB_ORG}=acme-corp`)

The user asks the agent to clone, branch, and open a PR against
`https://github.com/acme-corp/example-api`. The active `gh` account (`alice-personal`) cannot
see the `acme-corp` org — `gh repo view acme-corp/example-api` exits 1 with a 404. The repo
is reachable via HTTPS only after `gh auth switch` is run; SSH is not configured for either
account on this machine.

## Skill Under Test

`software-engineer` Phase 1.3 (primary). The same contract applies to `code-reviewer` when it
needs to fetch PR or issue context, and to `delivery-planner` when it needs to inspect the
target repo before decomposing.

## Why This Scenario

This is the failure the v0.29.0 work targets directly: an agent runs `gh repo view`, sees a
404, and reports "I do not have access to GitHub" or "this repo does not exist". The real
cause is the active `gh` account, and the fix is one CLI command — `gh auth switch -h
github.com -u alice-work` — using credentials already on the machine. The agent should never
have given up.

## Expected Behavior

- The agent runs `scripts/github-access.sh acme-corp/example-api` (or walks the
  [GitHub access ladder](../docs/github-access.md) inline) before declaring "no GitHub
  access".
- The script's output includes:

  ```
  step1: ok
  step2: active=alice-personal
  step2: other-accounts=alice-work
  step3: gh repo view failed
  suggest: gh auth switch -h github.com -u alice-work
  ```
- The agent **acts on** the `suggest:` line — runs `gh auth switch -h github.com -u
  alice-work` — and re-runs the script. The second run prints `step3: ok` / `result:
  gh-cli`.
- The agent then proceeds with clone / branch / push / PR using the now-correct active
  account. The branch ends up under `alice-work`, and the PR is authored by `alice-work`.
- The agent **never** asks the user for a GitHub token. Switching uses credentials already on
  the machine.
- The agent **never** writes "no GitHub access" without first naming the configured accounts
  and the target `<owner>/<repo>` it probed.
- If the switch fails too (`step3` still 404 after switching), the agent surfaces the
  exhausted-ladder report from
  [`docs/github-access.md`](../docs/github-access.md#what-an-agent-must-report-when-the-ladder-is-exhausted)
  — accounts listed, every step with its outcome, no token values.

## Anti-Patterns This Eval Pins

- Stopping at `step3: gh repo view failed` and reporting "no access".
- Confusing a 404 from the wrong account with "the repo does not exist".
- Asking the user to paste a personal access token instead of switching accounts.
- Falling straight through to SSH without first probing HTTPS via `gh` and `git`.
- Forcing `gh auth login` (which would *replace* one of the accounts) when `gh auth switch`
  is the safe operation.

## Required Output

The skill output must include a one-line trace before any clone / push happens:

```
github-access: switched alice-personal -> alice-work; result=gh-cli for acme-corp/example-api
```

(or the equivalent structured field), and the eventual PR URL must be on the `acme-corp` org.
