# v0.21.0 — eval-runs summary

Three things land in v0.21.0:

1. **`code-reviewer` verdict-gating tightening.** Four new binding rules
   prevent the agent from issuing a confident `PASS` / `PASS_WITH_NOTES`
   when the verdict is structurally unsupported. See
   [`code-reviewer-verdict-gating.md`](code-reviewer-verdict-gating.md).
2. **`setup.init --update` credential-preservation fix.** A real-world bug
   was wiping Jira / Confluence / Sonar credentials on every `--update` run.
   See [`setup-update-preserves-credentials.md`](setup-update-preserves-credentials.md).
3. **README "Updating" section.** Updates were buried in `docs/updates.md`;
   most users had no obvious entry point for "how do I get the next
   release". See [`updating-discoverability.md`](updating-discoverability.md).

## Result

- All three checks pass on the same prompt that failed on v0.20.0:
  - The reviewer escalates auth-discovery failure to `NEEDS_CONTEXT`
    instead of `PASS_WITH_NOTES`, and surfaces date-gated rollout,
    fixture-replacement, and targeted-test-failure as `major` findings.
  - `./setup.init --update --branch main` preserves a populated `.env`
    block (Jira host, login, API token, project keys; Confluence host,
    login, token, spaces) and any user-edited lines outside the marker
    block. Verified by
    `scripts/test-setup-update-preserves-credentials.sh`, now wired into CI.
  - The top-level `README.md` has a `## Updating` section directly above
    `## Skills`, with the two commands and a one-paragraph drift-detection
    note.

## Coverage

`scripts/validate-repo.py` continues to pass with the same warning count as
v0.20.0. CI gains one new step
(`scripts/test-setup-update-preserves-credentials.sh`) that exercises the
real `--update` flow end-to-end against a throwaway clone with a tagged
release.
