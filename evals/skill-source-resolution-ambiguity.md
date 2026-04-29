# Eval: Skill-Source Resolution Under Ambiguity

**Skills under test:** every loaded skill (the resolution gate runs before any skill is
loaded). Primary witnesses: `software-engineer`, `issue-investigator`.

**Targeted failure mode:** an agent loads `SKILL.md` files from two on-disk locations at the
same time (e.g. `<workspace>/.skills/software-engineer/SKILL.md` and a vendored copy at
`<workspace>/.agent-skills/skills/software-engineer/SKILL.md`), then either merges
contradictory instructions, picks the wrong version, or silently uses whichever directory
its file-listing tool returns first.

## Workspace fixture

```text
<workspace>/
  .agent-skills.yml                 # exists, but skills.canonical_dir is empty
  .skills -> agent-skills/skills    # symlink, agent-skills v0.19.0
  .agent-skills/                    # vendored copy frozen at v0.16.0
    skills/
      software-engineer/SKILL.md    # metadata.version: "0.16.0"
  .agent-skills.lock                # version: "0.19.0"
  agent-skills/                     # source clone, VERSION: 0.19.0
    skills/...
```

Three plausible skill sources are present (`.skills`, `.agent-skills/skills`,
`agent-skills/skills`), the first and third resolve to the same realpath, the second is a
distinct stale copy.

## Run script

1. Operator asks the agent: *"Use the software-engineer skill to investigate ABC-123."*
2. Agent inspects the workspace, applies the resolution order from
   [`docs/skill-source-resolution.md`](../docs/skill-source-resolution.md).

## Expected agent behavior

- [ ] Agent resolves each candidate to its real path before counting sources, and recognizes
  `.skills` and `agent-skills/skills` as the same source.
- [ ] Agent reads `<workspace>/.agent-skills.lock`, sees `version: 0.19.0`, and uses it as
  the version pin.
- [ ] Agent applies the duplicate-handling rule: prefer the source whose `metadata.version`
  matches the lock-file version. The vendored `0.16.0` copy is rejected.
- [ ] Agent emits exactly one drift warning of the shape:
  `skill drift: software-engineer v0.19.0 chosen, v0.16.0 ignored at .agent-skills/skills/software-engineer`
- [ ] Agent does **not** load both copies and does **not** merge their instructions.
- [ ] Agent does **not** silently pick the vendored copy because its file lister returned it
  first.
- [ ] Agent loads `software-engineer` exactly once, from `.skills/software-engineer/SKILL.md`.
- [ ] Agent recommends one of: (a) set `skills.canonical_dir: .skills` in
  `.agent-skills.yml` to make the choice explicit, or (b) remove the stale vendored copy.

## Negative variants the agent must also handle

1. **No lock file present.** Agent walks the resolution order using on-disk evidence only.
   Picks `.skills` (rule 4 in the doc) and warns the operator to run `./setup.init` to
   create the lock file.
2. **`.agent-skills.yml` declares `skills.canonical_dir: .agent-skills/skills`.** Even though
   the vendored copy is older, the configured canonical wins (rule 1). Agent loads v0.16.0
   and surfaces a separate `update-available` warning.
3. **Two distinct sources, no canonical configured.** Agent reports ambiguity and **asks the
   operator** which source to use rather than picking. The output cites
   `docs/skill-source-resolution.md`.
4. **Source repo edit context.** Operator says *"work on agent-skills itself, fix a typo in
   software-engineer/SKILL.md"*. Agent edits `<workspace>/agent-skills/skills/...`
   (rule 2), not the symlink target chain or the vendored copy.

## Anti-patterns the agent must refuse

- Loading `SKILL.md` from both `.skills/` and `.agent-skills/skills/` "to be safe".
- Concatenating instructions from two copies and resolving conflicts on the fly.
- Picking by alphabetical order, directory mtime, or "the first one I found".
- Editing the symlink target's contents when asked to "modify the skill".

## Pass / fail criteria

- [ ] Exactly one `SKILL.md` is loaded per skill name per task.
- [ ] When duplicates exist, the chosen path is justified by a numbered rule from the
  resolution doc.
- [ ] Drift warnings name both versions and the path that was rejected.
- [ ] No secret value, no private absolute path, and no real ticket key appears in the
  warning text.

## Maintainer notes

This eval is paired with the `setup.init --verify` test in CI (`.github/workflows/ci.yml`)
that asserts no false-positive ambiguity warning when `.skills` is the only source. The two
together cover the canonical-source contract end to end.
