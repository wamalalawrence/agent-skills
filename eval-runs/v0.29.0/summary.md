# v0.29.0 Eval Run Summary

Focus: closing the three recurring agent-failure modes the user surfaced in the v0.28.0 → v0.29.0
window — agents repeatedly asking where `.env` / `.jira-config.yml` are, agents giving up on
GitHub access without trying the most obvious fix (switch the active account), and per-task
cleanup destroying knowledge that the next task on the same project would have benefited from.

## Scenarios Added

- [`config-locator-parent-workspace`](../../evals/config-locator-parent-workspace.md): pins the
  rule that an agent at the repo cwd must run `scripts/locate-config.py` before declaring `.env`
  / `.jira-config.yml` missing. The files live in the **parent workspace folder**, where
  `setup.init` writes them.
- [`github-access-account-switch`](../../evals/github-access-account-switch.md): pins the
  GitHub access ladder. With two logged-in `gh` accounts, a 404 from `gh repo view` is "wrong
  active account", not "no access". The agent must run `scripts/github-access.sh
  <owner>/<repo>` and act on its `suggest: gh auth switch …` line before giving up.
- [`project-memory-read-and-survive-cleanup`](../../evals/project-memory-read-and-survive-cleanup.md):
  pins read-on-start, mid-task append, and the post-completion cleanup order (memory first,
  per-task scratch next via `scripts/project-memory.py cleanup-task <issue-key>`, local merged
  branches last). Verifies that `_projects/<slug>/memory.md` survives every cleanup pass.

## Result

`python3 scripts/validate-repo.py` and `python3 scripts/validate_skills.py` both exit 0 after
the new scripts, docs, evals, and `SKILL.md` updates land. Smoke tests on the three new scripts
all pass:

- `scripts/locate-config.py` correctly reports the searched-directory list and finds nothing in
  a bare cwd; finds the expected files when `.env` lives in the parent workspace folder.
- `scripts/github-access.sh wamalalawrence/agent-skills` walks the ladder and prints
  `step1: ok` / `step2: active=…` / `step2: other-accounts=…` / `step3: ok` / `result: gh-cli`
  on a multi-account machine.
- `scripts/project-memory.py` `init` / `note` / `read` / `cleanup-task` round-trip works,
  preserves `_projects/<slug>/` after `cleanup-task`, and refuses paths beginning with `_`.

Runtime dependency unchanged: agents must actually run the new scripts at the documented
points in each `SKILL.md`. The eval contracts above are the test surface for that.
