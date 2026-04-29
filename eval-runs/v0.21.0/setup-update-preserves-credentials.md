# v0.21.0 — setup.init --update preserves credentials

## The bug

In v0.20.0 and earlier, `./setup.init --update`:

1. Called `run_self_update`, which switched the source clone to the latest
   release tag and then hardcoded `JIRA_MODE="no"`, `CONFLUENCE_MODE="no"`,
   `SONAR_MODE="no"`, `ENVIRONMENTS_MODE="no"` before falling through to a
   non-interactive rerun of the main flow.
2. The main flow checked those modes and took the `else` branch in
   `write_env_block`, which wrote `JIRA_HOST=""`, `JIRA_LOGIN=""`,
   `JIRA_API_TOKEN=""`, `JIRA_PROJECT_KEYS=""`, the same for Confluence,
   and overwrote `ENVIRONMENTS_JSON` with `[]`.
3. `replace_generated_block` swapped the marker block in `<workspace>/.env`
   for the new (empty) one. `strip_managed_keys_outside_block` then removed
   any duplicate definitions outside the block, finishing the wipe.

Net effect: every `--update` silently blanked the user's Jira / Confluence
/ Sonar / Environments credentials. The next `code-reviewer` invocation
that depended on issue context reported "no Jira access" against a
workspace that had a fully-populated `.env` immediately before `--update`.

## Reproduction (v0.20.0)

```text
$ bash scripts/test-setup-update-preserves-credentials.sh
FAIL: expected line missing from .env: JIRA_HOST="https://jira.acme.example.com"
FAIL: expected line missing from .env: JIRA_LOGIN="alice@acme.example.com"
FAIL: expected line missing from .env: JIRA_API_TOKEN="SECRET-TOKEN-xyz123"
... (10 lines missing total)
```

## Fix (v0.21.0)

Two edits in `setup.init`:

1. `run_self_update` now sources the existing `<workspace>/.env` before
   handing off to the rerun, and sets `JIRA_MODE` / `CONFLUENCE_MODE` /
   `SONAR_MODE` / `ENVIRONMENTS_MODE` to `"yes"` whenever the
   corresponding required value (`JIRA_HOST` / `JIRA_API_TOKEN` /
   `CONFLUENCE_HOST` / `CONFLUENCE_API_TOKEN` / `SONAR_HOST_URL` /
   `SONAR_TOKEN` / non-empty `ENVIRONMENTS_JSON`) is present.
2. The main flow captures the sourced values in `EXISTING_*` variables
   before the unconditional `JIRA_HOST=""` / `CONF_HOST=""` /
   `SONAR_HOST_URL_VAL=""` resets, then uses those values as the prompt
   defaults. Non-interactive `prompt` and `prompt_secret` calls now fall
   back to the `EXISTING_*` value instead of writing an empty string when
   `ASSUME_YES=true`. The `ENVIRONMENTS_JSON` interactive loop is skipped
   in non-interactive mode and the existing JSON is preserved verbatim.

The fix is opt-out only by explicitly passing `--no-jira` or `--no-confluence`
on a future `setup.init` run, which still works.

## Regression test

`scripts/test-setup-update-preserves-credentials.sh` builds a throwaway
clone of `agent-skills`, tags it, writes a workspace `.env` with realistic
Jira+Confluence values plus a user-edited line outside the marker block,
runs `./setup.init --update --branch main`, and asserts every value is
preserved. The test is wired into `.github/workflows/ci.yml` so it runs on
every PR and push.

## Result

```text
$ bash scripts/test-setup-update-preserves-credentials.sh
ok: setup.init --update preserved Jira / Confluence credentials and user-edited lines
```

## Migration

If a user already ran `--update` on v0.20.0 and lost their credentials,
re-run `./setup.init` interactively (without `--update`) to fill them back
in. There is nothing else to migrate; the marker-block rewrite on the next
`--update` will pick the values up again from `.env` thanks to the
preservation logic.
