# Eval Run — model-routing knob removal (v0.20.0)

## What was removed

- `CODE_REVIEWER_MODEL` from `.env.example`.
- `code_reviewer_model` from `.agent-skills.example.yml`.
- The `CODE_REVIEWER_MODEL` row from `docs/configuration.md`'s
  `local-workspace` env table and the `code_reviewer_model` row from the
  `in-repo` YAML key table.
- The `CODE_REVIEWER_MODEL: optional` bullet from
  `skills/software-engineer/skills/code-reviewer/SKILL.md` Required Environment
  list.
- The "`CODE_REVIEWER_MODEL` is optional when the host uses its default model
  routing" sentence from the nested `code-reviewer/README.md`.

## Why

The skill never invoked the value itself — it was a passive hint to "the host"
that no host actually consumed. In every real host (Copilot Chat, Claude Code,
Cursor, Continue, Windsurf, ChatGPT desktop) the model is already chosen by the
user before the prompt reaches the skill. Adding a second knob inside the skill
spec did three things, all bad:

1. Made operators think they had to set it (the literal-`default` sentinel was
   itself confusing — see CHANGELOG v0.13.0 for the previous attempt to clarify
   the sentinel; the rewrite did not solve the underlying "should this even
   exist" question).
2. Generated repeated noise in `.env.example` (a 25-line block of model-id
   examples that drifted out of date as new models shipped).
3. Required the `code-reviewer` skill spec to list a fake env var inside its
   Required Environment list, taking attention away from variables the skill
   actually reads (`CODE_REVIEWER_BLOCKING`, `CODE_REVIEWER_MAX_FILES`,
   `CODE_REVIEWER_MAX_DIFF_CHARS`, `CODE_REVIEWER_*_SEVERITIES`,
   `CODE_REVIEWER_MAX_ROUNDS`, `CODE_REVIEWER_CACHE_DIR`,
   `CODE_REVIEWER_CACHE_TTL_HOURS`).

## What was kept

All other `CODE_REVIEWER_*` knobs are kept — they are real behavior switches
that the skill workflow does consume.

## Migration

A user upgrading from v0.19.0 or earlier:

- Existing `.env` files that still have `CODE_REVIEWER_MODEL="default"` continue
  to work — nothing reads the value, so it is inert. The variable can be
  removed at the user's convenience; `setup.init` does not own the line and
  will not touch it.
- An `.agent-skills.yml` carrying `code_reviewer_model: ""` is similarly inert.

The `scripts/validate-repo.py` `check_no_code_reviewer_model` validator forbids
re-introducing the variable in **this repository's** tracked files (excluding
the changelog entry that documents the removal and these eval-run notes that
discuss the migration). It does not run in user repositories.

## Verification

```text
$ python3 scripts/validate-repo.py
ok: repository validation passed with N warning(s)
```

Pass.
