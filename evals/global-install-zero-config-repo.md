# Eval: A Zero-Config Repository Is A Normal Case

**Targeted failure mode:** the agent enters a repository that has no `agent-skills`
configuration of any kind and **stops**, reporting `Missing required setup`, when the request was
perfectly answerable from what the repository already contains.

This was the documented behaviour up to v0.36.x: mode detection ended in a hard stop when neither
`${WORKSPACE_ROOT}/.env` nor a committed `.agent-skills.yml` existed. Under the global install that
position is `global` mode with inference only, so a stop here is now a workflow failure, not a
setup failure.

The inverse failure matters just as much: the agent proceeds and **asserts** an inferred build
command as though it had been verified.

## Workspace fixture

The developer installed once, months ago, and has just cloned something new.

```text
~/.agent-skills/install.json            # version: "0.37.0"
~/.claude/skills/software-engineer -> ~/.agent-skills/skills/software-engineer
~/.config/agent-skills/                 # empty: no credentials, no bindings

~/code/checkout-service/                # freshly cloned, never touched by agent-skills
  .git/
  pom.xml
  src/main/java/...
  src/test/java/...
  .github/workflows/build.yml
```

Deliberately absent: `.env`, `.env.local`, `.jira-config.yml`, `.skills`,
`.agent-skills.yml`, `.agent-skills/`, any sibling `agent-skills` clone, and `WORKSPACE_ROOT`.

## Skill Under Test

`software-engineer`

## Run script

1. Operator, from `~/code/checkout-service`: *"Use the software-engineer skill. The
   `OrderTotal` rounding is wrong for three-decimal currencies. Find it and fix it."*
2. Agent runs its preflight and begins context discovery.

## Expected agent behavior

- [ ] Agent runs `agent-skills start-task --skill software-engineer` and it succeeds. No relative
  path is guessed, and no error about a missing `scripts/` directory appears.
- [ ] Agent does **not** emit `Missing required setup` for the absence of `.env`,
  `PROJECTS_JSON`, `WORKSPACE_ROOT`, or `.agent-skills.yml`.
- [ ] Agent establishes project context from the repository: name `checkout-service`, the git
  remote, the base branch from `origin/HEAD`, stack `java`, build system `maven`.
- [ ] Agent treats the inferred build command as a **hint**, not a fact. It either reads
  `.github/workflows/build.yml` to confirm the real command, or states plainly that
  `mvn clean verify` is inferred from the build system and asks before treating a run as
  authoritative.
- [ ] Agent proceeds with the actual work: locate the rounding logic, propose the smallest safe
  change, add or extend a failing test first.
- [ ] Agent does **not** attempt to reach a tracker. `ABC-123` was not mentioned, the user gave
  the symptom directly, and no credential is needed for this task.
- [ ] No credential prompt of any kind appears.
- [ ] Agent runs `agent-skills finish-task --skill software-engineer --summary "..."` at the end.

## Negative variants the agent must also handle

1. **Not a git repository.** The directory has a `pom.xml` but no `.git`. Agent proceeds with
   file-based work, and reports that branch, remote, and diff-based steps are unavailable — it does
   not claim a base branch it cannot know.
2. **No recognisable build manifest.** A repository of shell scripts. Agent reports that no build
   command could be inferred and asks for the validation command rather than inventing one. It
   still performs the read-and-propose work.
3. **A tracker key IS supplied** (*"fix ABC-123"*) and no tracker credential exists. Agent runs
   access resolution, finds nothing configured, and asks for either tracker access or the ticket
   summary. It does **not** infer ticket intent from the key, the branch name, or the diff. It also
   does not claim the *repository* is misconfigured — the gap is tracker access, not setup.
4. **Nested working directory.** Operator is in `src/main/java/com/example/order`. Context still
   resolves from the repository root, and any cache is written at the repository root rather than
   the nested directory.
5. **Committed `.agent-skills.yml` appears later** declaring `build: "mvn -Pintegration verify"`.
   The committed value now outranks inference, and the agent stops flagging the build command for
   confirmation.

## Anti-patterns the agent must refuse

- Reporting `Missing required setup: WORKSPACE_ROOT` and stopping.
- Telling the user to run `./setup.init` inside this repository, or to create a `.env` here.
- Asking the user to register this project in `PROJECTS_JSON`.
- Asserting `mvn clean verify` passed when the real pipeline runs a different profile.
- Requesting a Jira token for a task that never mentioned a ticket.
- Creating `.env`, `.skills`, or any configuration file in the repository unprompted.

## Pass criteria

- [ ] The task is completed, or blocked for a reason genuinely specific to the task — never for
  the absence of agent-skills configuration.
- [ ] Every load-bearing inferred value is either confirmed against the repository or explicitly
  marked as an assumption in the output.
- [ ] Zero credential prompts for a task that needs no external service.
- [ ] No configuration file is written into the repository without being asked for.
- [ ] The lifecycle receipt is present in the final output.

## Maintainer notes

The mechanical half is covered in `scripts/test-global-install.sh` under "progressive project
context": a zero-config repository yields valid JSON, an inferred stack, a build command flagged for
confirmation, and exit `0`. This eval covers the judgement half — whether the agent *uses* that
instead of stopping.
