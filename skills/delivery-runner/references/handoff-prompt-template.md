# Handoff-Prompt Template

The binding shape of the prompt `delivery-runner` hands to each **fresh,
empty-context** agent when it dispatches a phase. The goal is that the receiving
agent — which has no prior conversation history — can execute exactly one phase
correctly and write the continuity checkpoint the runner will verify.

Fill every `<...>` placeholder from the plan artifacts. Use repo-relative paths.
Do not paste large file contents; pass pointers and let the fresh agent read
them. Do not add work beyond the single dispatched phase.

When a pointer names an input past the large-input threshold, pass a Context
Optimizer pack id instead of the raw path where one already exists — a pack is
deterministic and cached, so the next phase reuses it rather than recompressing
the same file. See [docs/context-optimizer.md](../../../docs/context-optimizer.md).

## Template

```text
You are starting a fresh task with empty context. Execute exactly ONE phase of
an existing delivery-planner plan, then stop.

Work key: <work-key>
Task cache dir: <cache-dir>/<work-key>/

Read these, in order, before doing anything else:
1. Destination brief: <cache-dir>/<work-key>/destination.md
2. Plan index: <cache-dir>/<work-key>/phased-plan/README.md
3. Your phase (the ONLY phase you execute this run):
   <cache-dir>/<work-key>/phased-plan/<phase-id>-<slug>.md
4. Evidence pack (continuity record): <cache-dir>/<work-key>/evidence-pack.yml
   — if it is missing, follow the missing-evidence-pack recovery rule in
   skills/software-engineer/references/evidence-pack.md (reconstruct the minimal
   delivery_plan from the index + phase files; if you cannot, stop BLOCKED).

Plan branch (BINDING): <plan-branch>
This is the single branch ALL phases of this plan commit to. It was created by
delivery-planner. Do NOT create a new branch for this phase.
- Fetch the plan branch: `git fetch origin <plan-branch>`.
- If it exists remotely: `git checkout <plan-branch> && git pull origin <plan-branch>`.
- If it does NOT exist remotely and you are the first repo-mutating phase:
  create it from the project base branch (`git checkout <base> && git pull &&
  git checkout -b <plan-branch>`) and push it so subsequent phases can fetch it.
- If it does NOT exist remotely but a prior phase already had it as working_branch,
  stop with BLOCKED — the plan branch should have been pushed by the first phase.

Owner skill (BINDING): load and follow
<skill-source>/<recommended-owner>/SKILL.md from the canonical skill source.
This phase's recommended_owner is "<recommended-owner>". If that SKILL.md cannot
be loaded, or its name does not equal "<recommended-owner>", stop with
"BLOCKED: recommended owner skill unavailable" and list the paths you checked.
Do not substitute a different skill or a generic workflow.

Do this:
- Run the owner skill's full workflow for THIS phase only, including its own
  PREFLIGHT start-task.sh and closing finish-task.sh lifecycle wrappers.
- Honor the phase's scope (in/out), validation/exit criteria, and rollback
  notes. Do not start, edit, or "get ahead" on any other phase.
- Before any repo mutation, run the pre-work isolation gate (plan-branch gate,
  working_branch, base_branch, branch-isolation assertion, owner-skill
  verification) from skills/software-engineer/references/evidence-pack.md.
- Before returning, write the phase-continuity checkpoint to evidence-pack.yml
  (state -> done or blocked, completed_at/blocked_at, completed_by, summary,
  artifacts, validation, follow_up_context, the last_completed_* mirrors, and
  the recomputed current_dispatch_pointer), THEN regenerate
  phased-plan/README.md from the updated evidence pack. A chat-only summary is
  NOT a checkpoint.

Stop and report blocked (do not improvise) if: the owner skill is unavailable,
a prerequisite phase is not done, validation fails, the working branch equals
the base branch, or the phase would require a forbidden destructive action.

Final message MUST state: the phase id, its resulting state (done | blocked),
the evidence-pack path, the regenerated phased-plan/README.md path, and the new
current_dispatch_pointer.
```

## Filling rules

- `<plan-branch>` is the `plan_branch` from `phased-plan/README.md`'s YAML header
  and `evidence-pack.yml.delivery_plan.plan_branch`. The runner reads it from
  `delivery-run-next.py`'s `plan_branch` field. It is the single branch ALL
  phases of this plan commit to. When `null` / empty (planner ran without git
  access), instruct the first executor to create the branch from the convention
  and record it.
- `<phase-id>-<slug>.md` is the file matching `current_dispatch_pointer`; the
  runner gets the exact filename from `delivery-run-next.py` (`phase.phase_file`).
- `<recommended-owner>` is the phase's owner skill from the index phase table
  and the evidence pack — they must agree.
- `<skill-source>` is resolved per
  [skill-source resolution](../../../docs/skill-source-resolution.md), honoring
  any explicit path the user supplied.
- If the user asked to review each handoff before dispatch, the runner prints
  this filled prompt and pauses instead of auto-dispatching.
