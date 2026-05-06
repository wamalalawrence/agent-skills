# Eval: Owner Skill Verification vs IDE Listing

**Skills under test:** `software-engineer`, `manual-tester`, `test-automation-engineer`,
`product-owner`, `issue-investigator`, plus
[`docs/skill-source-resolution.md`](../docs/skill-source-resolution.md#owner-skill-verification-recipe).

**Targeted failure mode:** an executor agent is dispatched to a phase whose
`recommended_owner` is `test-automation-engineer` (or `manual-tester`). The host IDE — Cursor,
Continue, Copilot Chat, or a similar surface — does not list those skills in its curated
"available skills" panel, even though `<workspace>/.skills/test-automation-engineer/SKILL.md`
exists on disk. The agent reports "no installed skill by that name" and silently downgrades
to "execute the phase directly" or substitutes a different skill. This corrupts the plan: the
phase reads as `done` while the actual deliverables (regression tests, defect rows) were
never produced under the right workflow.

The user has already complained that they ran `./setup.init` and the `.skills/` symlink
exists, so the canonical source is on disk regardless of what the IDE panel surfaces.

## Input Context

A user runs `delivery-planner`. Phase 04 is:

```yaml
- id: phase-04
  recommended_owner: test-automation-engineer
  state: ready
```

The `evidence-pack.yml.delivery_plan.current_dispatch_pointer` is `phase-04`. The user opens
a fresh chat in Cursor (or any IDE whose skill panel only lists a curated subset) and types:

```text
Run the next phase.
```

The agent's host-supplied skill registry does not include `test-automation-engineer`, but the
canonical source `<workspace>/.skills/test-automation-engineer/SKILL.md` exists and is
readable.

## Expected Behavior

- The executor resolves the canonical skill source per
  [skill-source-resolution.md](../docs/skill-source-resolution.md). For a workspace that has
  run `./setup.init`, the canonical source is `<workspace>/.skills/`.
- The executor runs the
  [owner-skill verification recipe](../docs/skill-source-resolution.md#owner-skill-verification-recipe):
  reads `<canonical>/test-automation-engineer/SKILL.md` directly with the file-read tool,
  confirms its `name:` field equals `test-automation-engineer`, and records the verified path
  on `phases[phase-04].owner_skill_source`.
- The executor then **loads that file's workflow** and follows it. It does not require the
  IDE panel to surface the skill.
- The phase-continuity checkpoint includes `owner_skill_source: <verified-path>` and
  `completed_by: test-automation-engineer` (the loaded skill's `name`, not the agent's
  fallback).

## Must Not Do

- **Must not say "I don't see a separate installed skill file by that exact name, so I'm
  executing the test-automation phase directly."** The canonical file's presence on disk is
  authoritative; the IDE panel is not. This exact failure phrase, or paraphrases of it, is a
  hard fail.
- **Must not substitute** `software-engineer` (or any other skill) for
  `test-automation-engineer`. Substitution corrupts the plan even when the resulting code
  looks similar.
- Must not write `phases[phase-04].state: done` with `completed_by: software-engineer` when
  the phase's `recommended_owner` is `test-automation-engineer`. The owner mismatch is a
  blocker.
- Must not list "the IDE doesn't expose this skill" as a justification anywhere in the
  user-facing output. If the canonical file is genuinely missing, stop with
  `BLOCKED: recommended owner skill unavailable` and list the exact paths checked — not the
  IDE panel contents.
- Must not require the user to manually paste the skill source path into the prompt. The
  resolution order in [skill-source-resolution.md](../docs/skill-source-resolution.md)
  already covers `<workspace>/.skills/` after `./setup.init`.

## Pass / Fail Checklist

- [ ] Executor reads `<canonical>/<recommended_owner>/SKILL.md` directly via the file-read
  tool and verifies the `name:` field.
- [ ] `phases[<id>].owner_skill_source` is populated with the verified absolute path.
- [ ] When the canonical file is present, the executor loads it regardless of host-IDE
  panel contents.
- [ ] When the canonical file is genuinely missing, the executor stops with
  `BLOCKED: recommended owner skill unavailable` and lists every path it checked (not "the
  IDE didn't list it").
- [ ] No silent substitution to `software-engineer` or any other skill.
- [ ] `completed_by` on the checkpoint matches the phase's `recommended_owner`.
