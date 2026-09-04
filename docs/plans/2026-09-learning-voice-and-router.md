# Improvement Plan: Durable Learning, Human Voice, and a Single Entry Point

Status: **implemented in `v0.36.0`, except three deferred items.** Written 2026-09-04 against
`v0.35.0`; shipped the same day. See the
[implementation status](#implementation-status) below for what landed and what did not, and
[`CHANGELOG.md`](../../CHANGELOG.md) for the release entry.

The plan is kept as written rather than rewritten in hindsight, so the reasoning that produced
the release stays readable next to the result.

## Implementation status

| Plan items | Status |
| --- | --- |
| V1–V4 writing voice | shipped |
| B1–B4, B7, B8 repo knowledge tier | shipped |
| B5, B6 hooks and CI enforcement | shipped |
| R1–R7 `tech-lead` router | shipped |
| S1, S3, S7 capability report, `.gitignore` fix, docs | shipped |
| M1–M5 MCP policy and preference order | shipped |
| H1–H9 corpus health | shipped |
| **S2** keychain credentials | **deferred — needs the Cloud vs Data Center answer** |
| **S5** collapse the duplicated config surface | **deferred — needs a decision** |
| **S6** split `setup.init` | **deferred — needs a decision** |

The three deferred items are the ones this document flagged as needing a decision, and nothing
has changed that. S2's premise depends on open question 7 below: on Atlassian Cloud the official
remote MCP server removes the stored token entirely, and on Data Center it does not apply. The
MCP layer that shipped is what makes that decidable.

One thing the plan got wrong, worth recording: it treated the sequencing as six releases. In
practice the work landed as one, because the pieces turned out to be more coupled than the plan
assumed — enforcement needs the knowledge tier, the router needs the capability report, and the
capability report needs the doctor script that S1 introduced.

This plan answers seven requests:

1. Make skills learn continuously and keep that knowledge **inside the repository they work
   on**, readable before a task starts and updated when it ends.
2. Make everything a skill writes read as if a person wrote it — code comments, commit
   messages, PR bodies, tracker comments, document-store pages.
3. Add **one entry-point skill** so specialist skills no longer have to be invoked by hand,
   one at a time.
4. Take what is worth taking from
   [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code)
   (ECC).
5. Review whether `setup.init` provisioning access is the right approach.
6. Decide whether and how the skills should use MCP servers.
7. Anything else worth improving — my own read of the corpus, not a request.

Each section states what already exists, what is actually missing, and what to build. Read
the [verdict table](#verdict-summary) first if you want the short version.

---

## Verdict summary

| Request | Already built? | Real gap |
| --- | --- | --- |
| Continuous learning / memory | Mostly — three tiers, scripts, wired into all 9 skills | Not in the repo, not enforced, unbounded on read |
| Human-sounding writing | No | No voice contract anywhere; only concision rules exist |
| Single entry point | No | No router, no routing table, no dispatch for ad-hoc work |
| ECC learnings | Partly convergent | Determinism, confidence scoring, and recall budgeting are missing |
| Setup and access | Yes, extensively | Wrong model: it provisions secrets it cannot validate |
| MCP | Not at all | Worth adding as an auth fix and a preference order, not a bundle |
| Corpus health | — | Telemetry never consumed; validator blind spots; 450 duplicated lines |

---

## 1. Continuous learning and repository-resident memory

### What already exists

This is the request that is closest to done. The Company Brain
([`docs/company-brain.md`](../company-brain.md)) already defines three memory tiers with
working implementations, not just prose:

- **Per-task blackboard** — `scripts/blackboard.py`, sections `facts`, `assumptions`,
  `unknowns`, `decisions`, `artifacts`, `handoffs`, `skill_versions`.
- **Project memory** — `scripts/project-memory.py`, a Markdown file plus a JSON mirror with
  sections `Project facts`, `Build & runtime`, `Common gotchas`, `Recent tasks`.
- **Org memory** — `scripts/org-memory.py`, the cross-project tier plus a
  project-to-shared-library index.

Two lifecycle wrappers do the reading and writing in one command each:
`scripts/start-task.sh` (org read, project read or init, blackboard init) and
`scripts/finish-task.sh` (memory write, telemetry, then scratch cleanup — in that order, so
cleanup can never eat the durable tier).

All nine `SKILL.md` files open with a `PREFLIGHT` block that runs `start-task.sh` and says
plainly: *"The output IS your starting context. Do not re-discover facts already recorded in
project memory."* Promotion machinery exists too (`scripts/promote-rules.py`,
`scripts/outcome-recorder.py`), and telemetry is appended per project as NDJSON.

So the premise "an agent should not start from nothing" is already designed in. The problems
are in **where the knowledge lives, whether the loop actually runs, and what gets captured.**

### Gap A — the knowledge does not live in the repository

Memory resolves to `.cache/agent-skills/` and the project's own tooling gitignores it:
`.gitignore:11` lists `.cache/`, `setup.init` writes that ignore rule into new workspaces,
and [`docs/installation.md`](../installation.md) tells in-repo users to add `.cache/` to the
target repo's `.gitignore`.

Consequence: knowledge survives *sessions on one machine and one checkout*. It does not
survive a fresh clone, a CI runner, a cloud agent, a second laptop, or a teammate. The only
knowledge in the whole system that genuinely travels with a repository today is what
`domain-modeler` writes — `CONTEXT.md` and `docs/adr/*.md` — and no other skill is told to
read those.

### Gap B — the loop is advisory, so it is probabilistic

Nothing fails when memory is skipped. `scripts/validate-repo.py` requires nine `##` sections
in every skill (`Purpose`, `When To Use`, `Related And Reused Skills`, `Required Inputs`,
`Required Workflow`, `Expected Output Contract`, `Quality Standards`, `Guardrails`,
`Example Prompts`) and **`PREFLIGHT` is not among them**. A skill could delete its entire
preflight block and CI would still pass. The only self-check is a checklist bullet that ships
with its own escape hatch: *"...or the final status explains the blocker."*

ECC states the underlying problem well, from its own v1-to-v2 rewrite: instruction-driven
observation fires roughly 50–80% of the time because it depends on the model's judgement,
while hook-driven observation fires every time. `agent-skills` is currently in the
instruction-driven position, and ships no hooks at all (`.claude/settings.json` contains only
a Bash permission allow-list).

### Gap C — what gets captured is a changelog, not knowledge

`finish-task.sh` writes the `Recent tasks` bullet **automatically and unconditionally**.
Durable facts — the `Build & runtime` and `Common gotchas` lines that actually make the next
agent smarter — are written only if the agent remembered to pass `--gotcha`,
`--build-runtime`, or `--fact "Section::text"`. The default path therefore produces a task
log and calls it learning. Nothing reads the blackboard at finish time to lift verified facts
out of it, so an interrupted session loses everything it discovered.

### Gap D — recall is unbounded and unranked

`start-task.sh` prints the whole `memory.md`. There is no relevance ranking, no confidence,
no decay, and no token budget. `dedup` and `compact --keep 20` exist but nothing invokes
them, and org memory has no compaction at all. The tier designed to save context will
eventually be the thing consuming it.

### Gap E — concrete defects found while reviewing

- **Placeholder regex mismatch.** `ensure_skeleton` writes `- _No facts yet. ...` but
  `append_note`, `dedup_memory`, and `find_repeated_bullets` only skip `- _empty`. So the
  placeholder never gets replaced, lingers under every populated section, and — because
  `promote-rules.py` uses the same filter — can surface as a false org-promotion candidate
  once two projects share it.
- **Cache root depends on cwd.** The final fallback is `os.getcwd()` / `${PWD}`, not the git
  root. Starting a task from a subdirectory silently creates a second, empty memory store.
- **Slug collisions.** `slugify()` squashes non-alphanumerics, so two projects can share one
  memory file, and drifting auto-detected names can split one project across several slugs.
- **`domain-modeler` has no `Behavior Checklist`,** so it has no self-check for the
  lifecycle at all.

### What to build

**B1. A committed, repo-resident knowledge tier.** Add a fourth scope that lives in the
target repository and is reviewed like code:

```text
.agent-skills/knowledge/
  README.md            # how to read and amend this, for humans
  project.md           # curated durable facts: build, runtime, architecture map, conventions
  lessons/<slug>.md    # atomic, confidence-scored lessons
```

Scope model, borrowed from ECC's Memory Vault and adapted:

| Scope | Location | Trust | Travels with repo |
| --- | --- | --- | --- |
| task | `.cache/.../<issue-key>/` | scratch | no |
| local | `.cache/.../_projects/<slug>/` | unreviewed, noisy | no |
| repo | `.agent-skills/knowledge/` | human-reviewed in a PR | **yes** |
| org | `.cache/.../_org/` | promoted, cross-project | no |

Promotion from `local` to `repo` is a **diff in the PR**, so a human approves every fact
before it becomes durable, shared truth. That is the whole point: committed memory that
nobody reviews is just a slower way to be wrong.

**B2. Atomic lessons with confidence.** One trigger, one action, evidence attached — the
shape ECC settled on. Proposed front matter:

```yaml
id: testcontainers-needs-docker-socket
trigger: "before running the integration profile"
action: "export DOCKER_HOST first; the default socket path is wrong on this stack"
confidence: 0.7        # 0.3 tentative -> 0.9 near-certain
domain: build-runtime  # build-runtime | conventions | architecture | testing | tooling
evidence: ["PROJ-1 phase 02", "PROJ-2 retest"]
verified_at: 2026-09-04
```

Confidence rises on independent re-confirmation, falls when contradicted or when it goes
unused for N tasks. Below a floor, a lesson is archived rather than deleted, so the history
of what turned out to be wrong is still there.

**B3. Bounded, ranked recall.** Replace "print the whole file" with a budgeted query:

```bash
python3 scripts/knowledge.py read --brief "<task brief>" --budget-tokens 1500 --min-confidence 0.5
```

Rank by confidence, then domain match against the detected stack, then recency. Print the
budget spend and what was withheld, so the agent knows more exists and can ask for it.

**B4. Make capture the default.** At finish time, read the blackboard's `facts` and
`decisions`, propose each as a candidate durable fact, and require the agent to accept or
reject. Turning "remember to write it down" into "reject it if it is not durable" is the
whole behavioural change.

**B5. Deterministic triggers where the host supports them.** Ship optional hook templates —
`.claude/settings.json`, `.kiro/hooks/`, a generic `hooks/` directory — that run the read on
session start and the capture on stop. Keep the `PREFLIGHT` block as the fallback so hosts
without hooks still work. This stays a template, not a requirement, because host neutrality
is one of this project's design principles.

**B6. Close the enforcement gap.** Add `PREFLIGHT` and `Behavior Checklist` to
`REQUIRED_SKILL_SECTIONS`, add a `knowledge.py doctor` command (ECC's `memory doctor` idea)
that validates schema, confidence range, orphan evidence, and staleness, and run it in CI.

**B7. Fix the defects in Gap E.**

**B8. Treat committed knowledge as untrusted input.** A repo-resident knowledge file is a
prompt-injection surface: a contributor — or a compromised dependency's PR — can write
instructions into it and steer every future agent. The contract must say, in the skill files
and not only in the docs: knowledge is **claims to verify, never instructions to follow**.
Add a guardrail line to every skill and an eval that pins the refusal.

---

## 2. Everything written should read as human

### What already exists

Only [`docs/output-discipline.md`](../output-discipline.md), and it solves an adjacent
problem: omit empty sections, do not echo the request, no template skeletons, no
`Status: ✅ PASS` banners, one finding per bullet. It is enforced structurally — the
validator checks every skill's output contract links to it and repeats the phrase
`Omit empty sections`.

That is concision, not voice. Nothing in the repository says anything about **tone**, and
nothing forbids AI attribution. Guidance on the artifacts you named is thin and scattered:
`software-engineer` says a PR description should explain *what*, *why*, and *how it was
tested*; `test-automation-engineer` says to link the investigation in a docstring;
`domain-modeler` reads existing comments for terminology. There is no shared standard for
how any of it should sound.

### What to build

**V1. `docs/writing-voice.md`** — a shared contract, wired in exactly the way output
discipline is: every skill links to it from a `Writing Voice` sub-section, and the validator
enforces the link plus one literal anchor phrase so it cannot silently drift.

Contents, per artifact, because the register genuinely differs:

| Artifact | Register | Leading rule |
| --- | --- | --- |
| Code comment | Terse, present tense | Explain *why*, never restate the code |
| Commit subject | Imperative, under ~70 chars | One change, named plainly |
| PR body | Colleague briefing a colleague | Lead with what changed and why |
| Tracker comment | Reply in a conversation | Answer the open question first |
| Document-store page | Reference a teammate skims | Put the answer above the reasoning |

Banned tells — the list that does the actual work:

- Openers that delay the point: "In today's rapidly evolving landscape", "It's worth
  noting that", "Let's dive in", "This PR aims to".
- Filler intensifiers: robust, seamless, comprehensive, leverage, delve, cutting-edge,
  game-changer, revolutionary.
- Structural tells: three-bullet symmetry for its own sake, a heading per sentence, a
  closing summary that repeats the opening, an engagement question at the end.
- Attribution and persona leakage: "As an AI", "Generated with", `Co-Authored-By` trailers
  for a model, emoji section headers.
- Restating the ticket back to the reader before saying anything new.

Positive rules: lead with the concrete change; prove with evidence instead of adjectives;
one idea per paragraph; keep the reader's next action obvious; stop when you are done.

**V2. Honesty boundary — explicit, because it is the one real risk here.** Sounding human
must not become hiding limitations. The existing `Open Questions Or Missing Evidence`
sections, `needs-context` statuses, and "not verified" qualifiers stay exactly as they are.
Never claim a test ran that did not run. The goal is *good writing*, not concealed
provenance.

**V3. Make attribution configurable.** Some employers require disclosure that a change was
AI-assisted. Add to `.agent-skills.yml`:

```yaml
writing:
  ai_attribution: none    # none | trailer | footer
  voice_reference: docs/voice.md    # optional local style sample to match
```

Default `none` matches your request; `trailer` and `footer` exist so the same skills stay
usable somewhere with a disclosure policy. That decision belongs to the operator, not to a
skill file.

**V4. An eval that pins it.** `evals/writing-voice-human-tone.md`, following the pattern of
`evals/code-reviewer-concise-output.md`: a worked before/after PR body and Jira comment, so
regressions are visible in review rather than in production.

---

## 3. One entry point instead of nine

### What already exists

No router. No routing table. No decision tree. Four partial substitutes carry the load
today: the `README.md` skill catalog, the hand-written chains in
[`docs/starter-prompts.md`](../starter-prompts.md) (`product-owner -> software-engineer ->
manual-tester -> test-automation-engineer`), the wired-loop list in
[`docs/review-loops.md`](../review-loops.md), and the readiness verdicts in
[`docs/requirement-understanding.md`](../requirement-understanding.md). Cross-skill
"delegation" is prose telling whoever is reading to load another skill next.

The one real dispatcher is `delivery-runner`, and it is deliberately narrow: it refuses to do
anything without `phased-plan/README.md` plus `destination.md`, and it refuses single-phase
work. Its machinery is exactly what a router needs, though — resolve the owner skill by
reading the file and checking its `name`, fill a binding handoff prompt, open a
fresh-context agent, verify from artifacts rather than chat, cap the iterations.

### The one constraint that shapes the whole design

[`docs/review-loops.md`](../review-loops.md) sets a **depth cap of two skills**, and it
overrides anything more permissive in individual skill files. A router that *loads*
`software-engineer` into its own context is already three deep, because
`software-engineer` invokes `code-reviewer`.

So the router must **dispatch, not invoke** — the same argument `delivery-runner` already
won: the dispatched agent is the root of its own call chain, and the router never appears in
it. This is not a technicality to work around. Get it wrong and the review bound that keeps
the engineer/reviewer loop honest quietly stops holding.

### What to build

**R1. New top-level skill `tech-lead`.** Role-shaped, consistent with the existing naming
(`product-owner`, `software-engineer`, `delivery-planner`). Alternatives if you dislike it:
`engineering-lead`, `delivery-lead`, `work-router`. It is the only skill you invoke; it reads
like a lead triaging an inbox.

Workflow:

1. Preflight — `start-task.sh`, plus the repo-tier knowledge read from section 1.
2. Classify the request: change, bug, question, refinement, test design, terminology,
   review, or oversized work.
3. Run the [requirement-understanding gate](../requirement-understanding.md). Confidence
   `unknown` or `low` routes out for clarification instead of guessing.
4. Route by the table below, dispatch a fresh-context agent, verify from artifacts, then
   either advance the chain or stop.
5. One `finish-task.sh` for the whole run, with a routing receipt.

**R2. The routing table, with one source of truth.** Derive it from
[`docs/skill-boundaries.md`](../skill-boundaries.md) rather than restating it, so the two
cannot drift:

| Signal | Route to | Because |
| --- | --- | --- |
| Product intent unclear | `product-owner` | Boundary rule: intent is never invented |
| Expected vs actual unclear | `issue-investigator` | Root cause precedes any fix |
| Too large for one session | `delivery-planner` then `delivery-runner` | Decompose, then run |
| Code change, intent clear | `software-engineer` | Owns implementation and review gates |
| Needs manual validation | `manual-tester` | Owns scenarios and defect evidence |
| Stable scenario to automate | `test-automation-engineer` | Owns level choice and fixtures |
| Term or decision to record | `domain-modeler` | Owns glossary and ADRs |
| Diff review only | `code-reviewer` | Owns verdict, not implementation |

**R3. Chains, not just single hops.** For "build this feature", the lead dispatches
`product-owner`, verifies the refinement artifact, dispatches `software-engineer`, and so on.
Each hop is a fresh agent reading persisted artifacts — the same "persistent artifacts, not
chat" rule the rest of the repo already follows.

**R4. Stopping conditions.** Never invent a route. If classification confidence is low, ask
**one** focused question. If the owner skill cannot be resolved by file read, stop with
`BLOCKED: owner skill unavailable` and list the paths checked. If a dispatched agent comes
back blocked, stop — do not retry a genuine blocker.

**R5. Auto-activation.** Write the `description` front matter for model-triggered discovery
and give it `user-invocable: true` with `disable-model-invocation: false` (only the two
nested skills use those keys today). It must win description-matching against the seven
existing skills, so it should describe *any* engineering request, not a niche.

**R6. Registration.** A new skill touches more files than you would expect. All of these
list the inventory: `README.md` (catalog, link refs, and the "seven top-level" count),
`scripts/validate-repo.py` (`REQUIRED_FILES` and `LINK_REQUIREMENTS`),
`docs/skill-boundaries.md`, `docs/review-loops.md` (with an explicit "adds no loop level"
note, as `delivery-runner` has), `docs/starter-prompts.md`, `docs/quickstart.md`,
`docs/README.md`, `docs/examples/`, `CHANGELOG.md`, `ROADMAP.md`, and `evals/`. Also:
`metadata.version` must equal `VERSION` in every skill, so adding one means the release bump
touches ten files.

**R7. Direct invocation stays.** The lead is an addition, not a replacement. Anyone who
already knows they want `code-reviewer` should keep invoking it directly, and the existing
starter prompts should keep working.

---

## 4. What to take from ECC

ECC is MIT-licensed, roughly 68 agents, 286 skills, hooks, rules, memory, and a security
scanner. It is a much broader system than this one. Breadth is not the thing to copy —
`agent-skills` competes on depth of a few roles, and 286 skills would dilute that. Four of
its ideas are worth taking, and they happen to be the four that fix real gaps above. Ideas
only; no code copied. Content below is paraphrased from ECC's own documentation.

| ECC idea | Take it? | Where it lands here |
| --- | --- | --- |
| Hooks over instructions for reliability | **Adopt** | B5 — deterministic read and capture |
| Atomic instincts, confidence 0.3–0.9, evidence-backed | **Adopt** | B2 — lesson schema |
| Bounded, ranked recall (cap injected items, confidence floor, stack relevance) | **Adopt** | B3 — recall budget |
| Scope model with a committed, human-reviewed tier | **Adopt** | B1 — repo tier |
| `memory doctor` validation command | Adopt | B6 — `knowledge.py doctor` |
| Promotion when a lesson recurs across projects with high confidence | Adapt | Adds confidence to the existing 2-project rule |
| Decay and pruning of unused learnings | Adopt | B2 — archive below the floor |
| Voice skill with an explicit banned-pattern list | **Adopt** | V1 — the model for the banned tells |
| Capability search ("which component fits this?") | Adapt | R2 — the router's discovery aid |
| Fresh-context review of the agent's own work | Already have | The engineer/reviewer loop |
| Background observer daemon | **Defer** | Fragile by ECC's own issue tracker on Windows; a hook plus finish-time extraction gets most of the value with none of the daemon |
| 286 skills, MCP bundles, plugin marketplace, dashboards | **Decline** | Wrong shape for a solo-maintained, host-neutral skill set |

The single most useful sentence in ECC's documentation, for your purposes, is its reason for
rewriting continuous learning: instruction-driven observation depends on model judgement and
misses cases, while hook-driven observation runs every time. Every "the agent skipped the
lifecycle wrapper" problem in this repo is that same finding.

Two things ECC does that this repo already does better: the depth-capped, artifact-based
review loop, and the destructive-action safety floor. Do not trade those away for breadth.

---

## 5. Setup and access: the model is inverted

Your instinct is right, and the problem is not code quality. `setup.init` is careful work:
safe-root guards that refuse `/`, `$HOME`, and system directories; idempotent marker blocks
that preserve edits outside them; `chmod 600`; duplicate-key migration for legacy files; a
warn-only credential blast-radius probe. The problem is what it is trying to do.

**In one sentence: it is a 2,162-line bash monolith that provisions credentials it cannot
validate, into a plaintext file, for tools it never checks exist.** Everything awkward
downstream follows from that.

### What it costs today

- **The tokens are never validated.** Three secrets are prompted (`JIRA_API_TOKEN`,
  `CONFLUENCE_API_TOKEN`, `SONAR_TOKEN`) and written literally into the `.env` managed block.
  The only network call in the whole script is `curl --head` against the *host*, and the code
  comment says any response including 401 counts as reachable "because credentials may not be
  valid yet". So `ok Jira host reachable` tells you nothing about whether the token works.
  `--verify` checks token **presence**, never validity.
- **Four diagnostics, none of which call each other.** `setup.init --verify`,
  `scripts/auth-preflight.py`, `scripts/locate-config.py`, and `scripts/github-access.sh` each
  answer part of "did my setup work?". `--verify` never runs the auth preflight and never walks
  the GitHub ladder, so "Verification passed" is compatible with a completely unusable tracker
  and GitHub setup. There is no `--doctor`.
- **89 fillable keys across three templates for roughly 25 unique concepts.** Only four are
  actually required (`WORKSPACE_ROOT`, `ORG_NAME`, `GITHUB_DEFAULT_BRANCH`, `PROJECTS_JSON`),
  but nothing distinguishes required from optional without reading the annotations. Jira host,
  login, and auth type exist in **three** places: `.env`, `.agent-skills.yml`, and
  `.jira-config.yml`.
- **One gotcha is documented in four separate files.** `${VAR}` placeholders in
  `.jira-config.yml` do not self-expand, and that is warned about in the example file,
  `.env.example`, `docs/auth-discovery.md`, and `docs/quickstart.md`, plus a troubleshooting
  row. Needing four warnings for one file format means the format is wrong, not that readers
  are careless.
- **`locate-config.py` exists purely to undo a layout decision.** Its own docstring says
  agents keep reporting "I can't find `.env`" when the file is one directory up — because
  `setup.init` writes config to the parent workspace folder, outside the repo. The fix is 187
  lines of Python plus a prose instruction in eight skill files telling the agent to run it
  before declaring config missing. If a model skips the prose, the dead end returns.
- **Non-interactive setup can never produce a working tracker.** `prompt_secret` returns the
  empty string with no TTY, and there is no `--jira-token`-style flag or environment
  passthrough. So `--yes --with-jira` writes a Jira block with an empty token, and no CI,
  Codespace, or scripted bootstrap can provision access.
- **All tool degradation is prose, not detection.** Skills mention `gh` 70 times, `git` 71,
  `mvn` 26, `jira` 6, `kubectl` 9. The fallback rules ("use the CLI first, fall back to REST")
  are instructions to a model. Nothing detects what is actually installed before the skill
  starts planning around it. `python3` is an undegraded hard dependency: without it, config
  location, auth preflight, and every memory feature stop working.

### One finding that is a real defect, not a design opinion

`setup.init`'s own security header says generated `.env` and `.jira-config.yml` "are added to
`.gitignore`". They are not, in the default layout. `update_workspace_gitignore` only creates a
missing `.gitignore` when `<workspace>/.git` exists — and the parent workspace folder normally
is not a repository. The caller's `skipped` branch prints nothing, so the operator is never
told. Harmless while that folder stays unversioned; a plaintext-token exposure the moment
anyone runs `git init` there. **Fix this first regardless of what else in this section you
accept.**

Two related sharp edges: `--verify` does `set -a; source "${env_file}"`, which is arbitrary
code execution from a config file (inherent to `.env`-as-bash); and
`scripts/github-access.sh` runs `git ls-remote` without `GIT_TERMINAL_PROMPT=0`, so on a
machine with no credential helper it can block on an interactive prompt inside what the agent
expects to be a non-interactive probe.

### What to build

**S1. Invert the model: detect capabilities, do not provision credentials.** The most useful
thing setup can hand an agent is not a token — it is an honest answer to "what can I actually
do here?". Add `scripts/doctor.sh` that runs the existing four diagnostics plus tool detection
(`gh`, `git`, `jira`, `python3`, `docker`, the project's build tool) and emits one capability
report. Fold that report into `start-task.sh` output so every skill starts knowing which
paths are open, instead of discovering it mid-task. This also converts the prose degradation
rules into something the agent reads rather than remembers.

**S2. Stop holding secrets the OS already holds.** Notice why the GitHub story works and the
Jira story does not: GitHub auth is delegated to `gh`, which owns the credential, so
`github-access.sh` only has to *probe*. Jira has no equivalent, so `setup.init` becomes a
credential vault. Two fixes, in order of preference: delegate to an already-authenticated
client where one exists (see [MCP](#6-mcp-worth-doing-but-as-an-auth-fix-and-a-preference-order),
which is the strongest option for Atlassian); and where a token must be stored, offer the OS
keychain (`security` on macOS, `secret-tool` on Linux) with `.env` as the explicit fallback.

**S3. Fix the `.gitignore` gap.** Write the block unconditionally, or refuse to write any
token until an ignore rule covering `.env` is confirmed present. Print the outcome either way.

**S4. Add a non-interactive credential path.** `--jira-token-env JIRA_API_TOKEN` reading the
value from the environment — never a flag value, which would land in shell history.

**S5. Collapse the config surface to one schema with two renderings.** The two execution modes
duplicate about 20 values in different shapes. Generate `.jira-config.yml` with values already
resolved at setup time, or drop the file and export the environment for the CLI. Either
removes the four-place gotcha.

**S6. Split `setup.init` and cover it.** 2,162 lines of bash with no library split, one
regression test, and a `--verify` that sources shell is a maintenance and safety liability.

**S7. Correct `docs/installation.md`.** Its flag table lists 11 flags and omits six that
exist: `--with-sonar`, `--no-sonar`, `--with-environments`, `--no-environments`,
`--no-connectivity-check`, `--no-credential-probe`.

---

## 6. MCP: worth doing, but as an auth fix and a preference order

Right now MCP appears in this repository exactly once — the line in section 4 above declining
ECC's MCP bundles. So this is a genuine gap, but the interesting question is not "should the
skills use MCP", it is "which layer does MCP belong at".

### The honest framing

MCP and skills are not competitors. MCP gives an agent typed access to external systems; a
skill teaches it how your team works. The current industry read is that they sit at different
layers and complement each other — see
[Agent Skills vs MCP](https://velt.dev/blog/agent-skills-vs-mcp-comparison-guide) and
[Skills vs MCP tools](https://blog.logrocket.com/skills-vs-mcp-tools-agent-guide/) for the
tradeoff, which is roughly auditability versus range.

The cost is context. Reported figures put a standard MCP setup at a large share of the context
window consumed before the agent takes its first action, a February 2026 paper examined 856
tools across 103 servers and found tool-description quality is a primary driver of token
inflation, and a commonly cited soft ceiling is around 20 active tools before selection
accuracy degrades. See
[From Tool Orchestration to Code Execution](https://arxiv.org/html/2602.15945v1) and
[token-efficient agents](https://effloow.hashnode.dev/mcp-code-execution-agent-efficiency-guide-2026).

That matters here specifically, because "token-conscious" is one of this repo's four stated
design principles. Bundling servers would spend the budget the whole design protects. ECC
reached the same conclusion from the other direction: it audited its defaults down from six
connectors to one and wrote a connector policy to keep it that way.

### The actual argument for MCP in this repo

Not capability — **auth**. Section 5's worst problem is that `setup.init` collects Atlassian
tokens in plaintext and cannot validate them. Atlassian now ships an
[official remote MCP server](https://github.com/atlassian/atlassian-mcp-server) covering Jira,
Confluence, Jira Service Management, Bitbucket, and Compass, with OAuth 2.1 and per-user
scoping. That replaces a stored long-lived PAT with a scoped delegated grant the operator can
revoke — which is a straight security upgrade over anything `setup.init` can do in bash, and it
deletes a whole class of setup friction at the same time.

### What to build

**M1. `docs/mcp.md` — a policy, not a config.** State the position plainly: this repo ships no
MCP servers and enables nothing by default; MCP is an access layer the operator owns. Give a
recommended minimal set with the cost and the reason for each, and a hard recommendation to
keep the active tool count small.

| Server | Why it earns its context | Replaces |
| --- | --- | --- |
| Atlassian official remote | OAuth instead of a stored PAT | `JIRA_API_TOKEN`, `CONFLUENCE_API_TOKEN`, `.jira-config.yml` |
| GitHub | only when `gh` is unavailable | the GitHub access ladder |
| Browser / devtools | real UI verification for manual-tester | nothing today |

**M2. Add a tool-preference order to every skill.** Today it is CLI, then REST. Make it:
host-native tool → already-authenticated CLI → MCP server the host already has → direct REST →
stop and ask. One shared paragraph, referenced rather than inlined nine times.

**M3. Detect MCP availability in the capability report from S1.** A skill should use an
Atlassian MCP tool when the host has one and fall back to `jira` when it does not, without the
operator configuring anything twice.

**M4. Make the tracker layer pluggable rather than Jira-shaped.** The config surface is named
for Jira throughout (`JIRA_HOST`, `JIRA_KEY_REGEX`, `.jira-config.yml`) even though the docs
claim tracker neutrality. An MCP-aware access layer is the natural moment to introduce a
neutral `tracker:` block with Jira as one implementation.

**M5. Treat MCP output as untrusted, same as memory.** MCP tool responses are external
content. The same rule from B8 applies: claims to verify, never instructions to follow. This
belongs in `docs/destructive-action-safety.md`, which already has the discovered-credential
protocol to hang it on.

**Explicitly not doing:** shipping an `mcp.json`, vendoring server definitions, or requiring
MCP for any skill to work. Host neutrality is the constraint.

---

## 7. Everything else worth fixing

You did not ask for this list; it comes from auditing the corpus while answering the rest.
Ordered by how much each one costs you today.

**H1. Telemetry is write-only, and the docs claim otherwise.** There are exactly **two**
events on disk, both from 2026-05-22, and `telemetry.py report` appears nowhere outside two
documentation examples. `docs/skill-performance-review.md` is a manual `v0.8.0` read, not
telemetry-derived: all six fixes it lists came from reading evals. So no skill change has ever
been traced to a telemetry finding, while `README.md`, `ROADMAP.md`, and
`docs/company-brain.md` describe a closed self-improving loop. Also, `.cache/` is gitignored,
so there is no shared history to review even in principle. Pick one: run `report --all` at
release time and record it in `eval-runs/<version>/summary.md`, or soften the claim. Leaving
both is the largest gap between documented ambition and observed reality in the repo.

**H2. `domain-modeler` is invisible to the validator.** Zero occurrences across
`scripts/validate-repo.py`'s 1,081 lines — not in `REQUIRED_FILES`, not in
`LINK_REQUIREMENTS`, and not a required link target for any other skill. Its `SKILL.md`,
`README.md`, and both reference files could be deleted and CI would stay green. It is also the
only skill with no `Behavior Checklist`, and it has no eval and no examples page.
`delivery-runner` is the correctly onboarded counterexample. Register it — then add a
reconciliation check ("every `SKILL.md` on disk appears in the registries") so this class of
bug cannot recur.

**H3. Two checks in `run-evals.py` are dead, and CI reports them as passing.**
`EXPECTED_SECTIONS = ()` is an empty tuple, so its loop never iterates; and the
`Expected Skills:` check matches **0 of 32** eval files. In the default configuration only two
things can actually fail: a missing top-level heading, and a missing `eval-runs/*/summary.md`.
Everything about eval *content* is warn-only or dead. Delete the dead checks so the harness
stops overstating itself.

**H4. About 450 lines of near-duplicate `PREFLIGHT` across nine skills.** Each carries 39–53
lines; `product-owner` and `manual-tester` differ on **5 lines out of 52**. Roughly 360 lines
are recoverable by extracting one referenced file plus a short per-skill stub. The same change
fixes a release chore: `--skill <name>=0.35.0` is hardcoded in nine places, so every version
bump edits nine files. Note the contrast with the output-discipline block, which is
duplicated **deliberately** and gated by `check_skill_output_discipline` — that one should
stay inline. `PREFLIGHT` has no such justification recorded and no gate.

**H5. `PREFLIGHT` is not enforced by CI.** `REQUIRED_SKILL_SECTIONS` has nine entries and
`PREFLIGHT` is not one of them. It is the load-bearing block for memory, blackboard, and
telemetry, held in place by convention alone. Same for `Behavior Checklist` (8/9 skills) and
`Stopping Conditions` (8/9 — `delivery-runner`, the autonomous one, is the exception).
This overlaps B6; do them together.

**H6. `software-engineer/SKILL.md` is 1,348 lines and about 11,000 words** — 3.3× the median
skill and 62% larger than the next biggest. The five workflow phases are 552 lines (41%) and
should stay. Two blocks totalling 190 lines are extractable without touching the workflow:
`Destructive Action Guardrails` (98 lines, restating a policy `docs/` already owns) and
`Required Environment` (92 lines, which S1's capability report would largely replace).

**H7. Eval headings have drifted, which blocks `--invoke`.** `Pass/Fail Checklist` appears 18
times and `Pass / Fail Checklist` 6 times, plus nine singleton headings, and one heading has a
markdown link baked into it. The harness grew alias lists to absorb the mess rather than the
corpus being normalized. Normalize first; then the 12 evals that already have
`Required Output Fields` give you a mechanical field-presence grader with no LLM judge needed
— the cheapest possible first version of `--invoke`.

**H8. Small factual drift.** `README.md:186` says "eight specialist skills" while `:96`
correctly says seven top-level plus two nested; add a count check tying prose to the glob.
`ROADMAP.md` still lists "four core delivery skills" and asks for a validation script that now
exists at 1,081 lines. There is no `eval-runs/` entry for the current release.
`scripts/delivery-run-next.py` is the one non-executable file in `scripts/` (mode 644 while
every sibling is 755) — it will fail if anything invokes it directly.

**H9. Only the two nested skills declare `user-invocable: true`.** The seven top-level
skills — the ones the README says are meant to be invoked directly — do not. That is the
inverse of what you would expect, and it matters for the router in section 3, which needs its
description and invocability flags to win against the existing seven. Decide the convention and
enforce it.

Two things the audit flagged that I checked and **rejected**: `scripts/task-context.sh` is not
dead code (both lifecycle wrappers source it as a shared bash library), and
`scripts/validate_skills.py` is not a stray stub (it is a deliberate seven-line
backward-compatible shim that re-runs the validator).

---

## Sequencing

Six releases, ordered by risk rather than by excitement. Voice first because it is pure
addition with the highest daily payoff; the router late because it depends on the knowledge
tier being trustworthy.

One item jumps the queue. The `.gitignore` gap in S3 is a latent plaintext-token exposure and
contradicts `setup.init`'s own security header, so it ships as a patch now, not in a release.

| Release | Items | Theme |
| --- | --- | --- |
| `0.35.1` | S3 | the `.gitignore` write gap |
| `0.36.0` | V1–V4, H1–H3, H8 | writing voice, then stop the docs overstating the system |
| `0.37.0` | B1–B4, B7, B8 | repo knowledge tier, lessons, ranked recall, default capture |
| `0.38.0` | B5, B6, H4–H6 | hooks, CI enforcement, extract `PREFLIGHT`, shrink the big skill |
| `0.39.0` | S1, S2, S4–S7, M1–M5 | capability report, credential delegation, MCP policy |
| `0.40.0` | R1–R7, H7, H9 | the `tech-lead` router, eval normalization, invocability |

Why that order:

- **S3 is a patch, not a release.** One function, latent secret exposure, no design debate.
- **Voice first** because it is pure addition with no architectural risk, and the honesty
  fixes beside it are small and stop the documentation describing a loop that is half-built.
- **Knowledge tier before enforcement.** There is nothing worth gating until the new tier
  exists, and extracting `PREFLIGHT` is the same edit as adding the gate for it.
- **MCP with the credential rework**, because MCP is the best available answer to S2 and
  doing them separately means rewriting the same auth paths twice.
- **Router last.** It should route with a working knowledge tier and a capability report to
  route on, not before.

Each release keeps the existing release checklist: validator green, evals updated, an
`eval-runs/<version>/summary.md`, and `metadata.version` aligned across every skill.

---

## Risks and open questions

Answer these and the plan is executable as written.

1. **Committed knowledge means PR noise and a prompt-injection surface.** Every task will
   want to touch `.agent-skills/knowledge/`. Acceptable? The alternative is a separate
   knowledge branch, which is cleaner in review but much easier to forget.
2. **Naming.** `tech-lead`, or one of `engineering-lead`, `delivery-lead`, `work-router`?
3. **AI attribution default.** Plan sets `none`. Confirm that matches your workplace
   policy — this is the one item where a wrong default has consequences outside the repo.
4. **Hook templates are host-specific.** Shipping them nudges this host-neutral project
   toward Claude Code and Kiro specifics. Templates in an optional directory, or leave hooks
   entirely to the user?
5. **Telemetry: consume it or soften the claim?** H1 offers both. Consuming it means a
   release-time ritual you have to actually perform; softening means admitting the loop is
   half-built. I lean toward consuming it, because the eval harness needs the same discipline.
6. **How far to take the setup rework?** S1 through S7 is a substantial rewrite of the most
   battle-tested file in the repo. A defensible smaller version is S3 plus S1's capability
   report plus S7's doc fix, leaving the credential model alone until MCP proves out.
7. **Is Atlassian OAuth via MCP actually available to you?** The whole S2/M1 argument assumes
   Atlassian Cloud. On self-hosted Data Center the official remote server does not apply and
   PATs remain the only option, which would keep `setup.init`'s current model necessary.

Two things I could not verify. First, whether the memory loop is being skipped in your real
sessions — the mechanism is clearly skippable, and the two telemetry events on disk are
consistent with "almost never run" but also with "the cache was cleared", so a
`telemetry.py report --all` over your workspace would settle it before we spend a release on
it. Second, the external MCP figures in section 6 are reported numbers from secondary sources,
not measurements from this repo; if MCP adoption hinges on them, measure your own host.

---

## A note on this document

The three external URLs cited in section 6 use hosts that are not in
`scripts/validate-repo.py`'s `ALLOWED_HOSTS`, so they raise three `review hardcoded hostname`
warnings. They are attribution for researched claims, so they stay. Either add the hosts to
the allow-list or drop the links if a clean warning count matters more.

---

## Source

External research: [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code),
MIT-licensed — its `README.md`, `skills/continuous-learning-v2/SKILL.md`,
`skills/article-writing/SKILL.md`, and `rules/common/git-workflow.md`. Content was rephrased
for compliance with licensing restrictions; no code was copied.
