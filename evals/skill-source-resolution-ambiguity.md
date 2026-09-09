# Eval: Skill-Source Resolution With More Than One Copy On Disk

**Skills under test:** every loaded skill (the resolution gate runs before any skill is
loaded). Primary witnesses: `software-engineer`, `issue-investigator`.

**Targeted failure mode:** an agent loads `SKILL.md` files from two on-disk locations at the
same time, then either merges contradictory instructions, picks the wrong version, or silently
uses whichever directory its file-listing tool returned first.

Rewritten for v0.37.0. Under the machine-global install the common shape changed: several host
directories now hold symlinks into **one** canonical tree, so multiple *paths* are normal and
harmless. What still matters is **version skew** — a vendored copy frozen at an older release.

## Workspace fixture

```text
~/.agent-skills/                        # global install, VERSION 0.37.0
  install.json                          # version: "0.37.0"
  skills -> <clone>/skills

~/.claude/skills/software-engineer  -> ~/.agent-skills/skills/software-engineer
~/.agents/skills/software-engineer  -> ~/.agent-skills/skills/software-engineer
~/.cursor/skills/software-engineer  -> ~/.agent-skills/skills/software-engineer

~/code/payments-api/                    # the repository being worked on
  .agent-skills.yml                     # exists; skills.canonical_dir is empty
  .agent-skills/
    skills/
      software-engineer/SKILL.md        # vendored copy, metadata.version: "0.16.0"
```

Four paths contain a `software-engineer/SKILL.md`. Three resolve to the same realpath at
`0.37.0`; the fourth is a genuinely distinct copy at `0.16.0`.

## Skill Under Test

`software-engineer`

## Run script

1. Operator asks the agent: *"Use the software-engineer skill to investigate ABC-123."*
2. Agent applies the resolution order in
   [`docs/skill-source-resolution.md`](../docs/skill-source-resolution.md).

## Expected agent behavior

- [ ] Agent resolves each candidate to its real path before counting sources, and recognises the
  three host paths as **one** source rather than three.
- [ ] Agent applies the order and selects the project-vendored copy, because rule 3
  (project-vendored) sits above rule 4 (global canonical) and the repository vendored it
  deliberately.
- [ ] Agent reads `~/.agent-skills/install.json`, sees `version: 0.37.0`, and uses it to detect
  skew against the loaded `0.16.0`.
- [ ] Agent emits exactly one drift warning of the shape:
  `skill drift: software-engineer v0.16.0 chosen, v0.37.0 ignored at ~/.agent-skills/skills/software-engineer`
- [ ] Agent does **not** load both copies and does **not** merge their instructions.
- [ ] Agent does **not** stop to ask which source to use. The order is total, so there is always a
  first match. Asking here would be the pre-v0.37.0 behaviour and is now wrong.
- [ ] Agent loads `software-engineer` exactly once.
- [ ] Agent surfaces the remediation: either refresh the vendored copy or set
  `skills.canonical_dir` explicitly.

## Negative variants the agent must also handle

0. **Explicit path supplied in the prompt.** Operator says: *"Use the skills at
   `~/.agent-skills/skills`; run the software-engineer skill."* Agent verifies that exact path
   first and loads from it. It must not report a default path as missing unless it also checked
   the supplied path and that path was unreadable.
1. **No vendored copy.** Only the global install and its host symlinks exist. Agent resolves to
   `~/.agent-skills/skills/software-engineer`, emits **no** drift warning, and does not report
   ambiguity merely because four paths listed the same file.
2. **`.agent-skills.yml` declares `skills.canonical_dir: .agent-skills/skills`.** Rule 1 wins
   explicitly; the same `0.16.0` copy is loaded, and the drift warning still fires.
3. **Source-repo edit context.** Operator says *"work on agent-skills itself, fix a typo in
   software-engineer/SKILL.md"*. Agent edits the source clone (rule 2), not the installed
   symlink target and not the vendored copy.
4. **Broken global install.** `~/.agent-skills/skills` is a dangling symlink because the clone
   was moved. Agent falls through to the vendored copy, and reports that the global install needs
   `agent-skills install` rather than presenting the stale copy as healthy.
5. **Legacy workspace.** A pre-v0.37.0 `<workspace>/.skills` exists and no global install does.
   Agent uses it (rule 5), works normally, and notes once that `agent-skills migrate` explains the
   move. It does not block.

## Anti-patterns the agent must refuse

- Loading `SKILL.md` from both the vendored copy and the global install "to be safe".
- Concatenating instructions from two copies and resolving conflicts on the fly.
- Picking by alphabetical order, directory mtime, or "the first one I found".
- Reporting ambiguity because several host directories listed the same physical file.
- Editing the symlink target's contents when asked to "modify the skill".

## Pass criteria

- [ ] Exactly one `SKILL.md` is loaded per skill name per task.
- [ ] Paths that resolve to one physical directory are counted once.
- [ ] A user-supplied skill path is verified before any host default.
- [ ] The chosen path is justified by a numbered rule from the resolution doc.
- [ ] Drift warnings name both versions and the path that was rejected.
- [ ] No secret value, no private absolute path, and no real ticket key appears in the warning.

## Maintainer notes

Paired with `scripts/test-global-install.sh`, which asserts mechanically that every host
registration resolves to one canonical realpath (`present=4 distinct=1`). This eval covers the
judgement half: what an agent must do when a copy genuinely differs.
