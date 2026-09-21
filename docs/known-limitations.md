# Known Limitations

`agent-skills` provides instructions and workflows. It does not provide deterministic software,
runtime enforcement, or guaranteed outcomes.

## Agent behaviour

- **Agent behaviour varies.** Different assistants follow the same `SKILL.md` with different levels
  of consistency, especially for nested skills.
- **Nested skill support is host-dependent.** Hosts that walk the skills root recursively find
  `software-engineer/skills/issue-investigator` and `.../code-reviewer` automatically. Hosts that do
  not still see the parent skill; reference the nested `SKILL.md` directly if a host does not surface
  it. Recursion behaviour is not documented for every host.
- **Generated output requires human review.** Plans, code, tests, acceptance criteria, defect
  reports, and reviews should be checked by a responsible human before use.
- **Nested dispatch cannot be detected by a script.** Whether an agent dispatched by Wamala can
  itself open a fresh agent depends on the host's tool registration inside that agent, which no
  command run from outside can see. Wamala establishes it from what a dispatched step reports,
  treats an unproven answer as unavailable, and walks a plan itself in plan mode. A host that can
  nest but never says so pays for that caution with a slightly larger dispatcher context, not with
  a broken run.
- **Independent review depends on the reviewer recording its own context.** `review.independence`
  is written by `code-reviewer`, which is the only party that knows whether it wrote the diff it
  judges. A reviewer that records `fresh-context` falsely defeats the sibling-review fallback.
  An absent field reads as `same-context`, so the failure mode is an extra review, not a missing one.
- **Some requests have no owner.** Authoring a visual design or a new design direction is not
  owned by any canonical skill. `product-owner` owns UX intent and `manual-tester` observes against
  a standard, but neither creates one. Wamala says so rather than routing it. See
  [known gaps](../skills/wamala/references/routing-table.md#known-gaps).
- **Company-specific standards are not bundled.** Repository conventions, coding standards, ticket
  formats, review rules, deployment practices, and architecture constraints must come from the user,
  the target repository, or attached documentation.

## Installation and host discovery

- **The global install is local only.** It lives in your home directory, so a cloud or remote agent
  cannot see it. Those environments need the in-repo mechanism. Cursor's Cloud Agents are the one
  partial exception, and only for `~/.cursor/skills` with sync explicitly enabled. See
  [execution-modes.md](execution-modes.md).
- **JetBrains needs one manual action.** Global skill directories are IDE settings state, not a
  filesystem convention, so nothing outside the IDE can register one safely. One entry under Settings,
  documented in [assistants.md](assistants.md). This is not zero-click and is not claimed to be.
- **Hosts may list a skill more than once.** Several hosts deliberately scan each other's global
  directories, and no arrangement of directories avoids that. Every registration is a symlink to one
  canonical tree, so a duplicate listing is the same file at the same version — but the listing itself
  is outside this project's control.
- **Host support is verified against documentation and filesystem behaviour, not against every host
  release.** Agent Skills support is moving quickly. `agent-skills verify` is the check that matters
  on your machine; this repository's table can lag a host update.
- **The install depends on the clone staying put.** Canonical trees are symlinks into the source
  repository. Move or delete the clone and the install breaks; `agent-skills verify` detects exactly
  that, and rerunning `agent-skills install` repairs it.
- **Native Windows is not supported.** Run under WSL or Git Bash. PowerShell-native installation, and
  Windows Credential Manager with it, are evaluated but not implemented.

## Credentials and access

- **External access depends on your tools and permissions.** A tracker, GitHub, a document store, CI,
  logs, and cloud environments are reachable only when the session has the right credentials and
  network access. See [access-resolution.md](access-resolution.md) for the order a skill must walk
  before reporting a service unavailable.
- **Resolution proves construction, not validity.** A resolved status means a correct request can be
  built. It does not prove the credential still works on the far side; a rotated token still returns
  401.
- **The file fallback is only as strong as filesystem permissions.** When no OS credential store is
  available, secrets go to a `0600` file in a `0700` directory outside every repository. That is
  reported every time, never silently substituted, and deliberately not encrypted — an encrypted file
  beside its own key would be theatre.
- **A lone compatible identity is used automatically.** That is what makes two repositories share one
  work account without re-entering a token, and a committed file cannot create or name an identity.
  It does mean a machine holding both production and sandbox identities for one service can resolve
  the wrong one if only one exists for that service. `AGENT_SKILLS_STRICT_BINDING=1` removes the
  automatic path.
- **Legacy plaintext exposure is not undone by migration.** Importing a token from a `.env` into the
  keychain moves it; it does not un-expose it. Rotate anything you believe was exposed.
- **On macOS the Keychain *write* passes the secret in argv.** `security add-generic-password` takes
  the value as an argument, so it is visible to a same-user `ps` for the duration of that one call.
  Reads are unaffected, and the file fallback never puts a value in argv. This is accepted rather than
  fixed because the obvious alternative is worse: piping the value on stdin makes `security` exit 0
  while storing an *empty* secret, which is silent credential loss. See
  [the security review](security-review-v0.37.0.md) for the measurements.
- **A repository may describe a service but never route a credential.** A file inside the repository
  cannot select an identity, and cannot supply a host that disagrees with the identity providing the
  secret. Where git cannot confirm a file is untracked, the file is refused rather than trusted — so
  on a machine with no `git`, or in a repository git refuses over ownership, a legitimate
  `.agent-skills.local.yml` stops working. Use `agent-skills access bind` or process environment
  variables there.
- **Resolution is not authorization.** Finding a credential grants no permission to act. The
  [destructive-action safety policy](destructive-action-safety.md) is a separate contract and still
  applies to everything a resolver reports as available.

## Project context

- **Inference can be wrong.** Build and format commands derived from a build system are hints. Anything
  not read directly from the repository is reported under `needs_confirmation` rather than asserted,
  but an agent that ignores that list will act on a guess.
- **A non-git directory has no branch, remote, or diff.** Inference degrades to the directory name and
  build manifests, and reports the gap.

## Context Optimizer

See [context-optimizer.md](context-optimizer.md) for the full treatment. The load-bearing ones:

- **Relevance heuristics can miss evidence.** Selection is deterministic pattern matching over the
  task brief plus structure, not comprehension. A brief that names nothing present in the input gets
  a pack built from severity and structure alone, and it says so — but "it said so" is not the same
  as "it found the answer".
- **No compression can prove the omitted content was irrelevant.** The omission records say what was
  dropped and how to get it back. They do not certify that it did not matter, and no algorithm can.
- **Token estimates are approximate.** The budget is in characters because provider tokenisation
  differs and making one provider's tokeniser a hard dependency would be a worse trade. Four
  characters per token is a planning heuristic, not a measurement of any specific model.
- **No claim of exact API-cost reduction.** Reductions are reported in characters. No figure in this
  repository was measured against a known model-and-pricing configuration, so no dollar claim is
  made.
- **Parsing support varies by format.** The JSON, YAML, and XML scanners are tolerant rather than
  conformant, which is deliberate — real evidence includes malformed and half-written payloads. It
  also means deeply unusual YAML, heavily namespaced XML, and JSON carrying documents inside strings
  are handled approximately.
- **Binary formats need external tooling.** A NUL byte in the first 8 KiB is refused rather than
  guessed at.
- **Generated and minified files are poorly structured by nature.** They are detected and
  deprioritised, but a single 4 MB line has no internal boundaries to select on.
- **Structure-bearing formats are read whole.** SQL, JSON/YAML/XML, source, and diffs need the text
  to find the shape and are capped by `--max-read-bytes`. Only logs and plain text stream.
- **Secret detection is pattern-based.** It covers the common token shapes and it is not a
  guarantee. An unrecognised internal credential format will pass through into a pack.
- **A pack is not a review.** For diffs especially, the pack states how much it covered. An agent
  that issues a verdict from a partial diff has misused it, and no mechanism here can prevent that
  — which is why `code-reviewer` owns verdicts.

## Meeting Intelligence

- The Recall adapter was built against Recall's published API reference and tested against
  fixtures derived from it, not against a live account. The opt-in smoke test
  (`AGENT_SKILLS_MEETING_LIVE_SMOKE=1 python3 scripts/test-meeting.py`) authenticates and lists
  bots; nothing in the suite creates a real bot.
- Extraction quality depends on the host model. The CLI's checks bound the damage — no invented
  evidence, no confirmed hedge, no widened scope, no unproven supersession, no unsupported owner —
  but cannot supply a fact the model missed or the right owner in place of a wrong one.
- The model-dependent evals in `eval-runs/v1.2.0/` were extracted by the same session that wrote
  the golden set. They show the pipeline preserves good extraction and neutralises bad
  extraction; they are not an unbiased measure of a model's extraction quality.
- Spoken-secret detection is heuristic and errs toward redaction.
- Only repository scope exists. There is no team or organisation knowledge store.
- `doctor` does not contact Recall unless `--probe-meeting` is passed.
- Processing is post-meeting; live transcript streaming and in-meeting interaction are not
  supported.

## Execution Guard

[Execution Guard](execution-guard.md) is a second layer, not a solution. Its limits are listed
in full in [its own section](execution-guard.md#known-limitations); the ones most often
overstated:

- **Coverage is per host, and four hosts have a blocking hook today.** For the rest the guard is
  advisory or wrapper-only. `agent-skills guard doctor` reports the real level per host, and
  never claims `enforced` where the hook is not actually registered.
- **It does not solve prompt injection.** It changes the *consequence* of a successful
  injection, because the resulting command still has to cross a deterministic gate. The content
  scanner reports `SUSPICIOUS_INSTRUCTION_SHAPED_CONTENT` — evidence for a reviewer — and
  deliberately does not claim to have found an attack.
- **Shell parsing has edge cases.** Aliases, shell functions, and variables only the live shell
  can expand are not knowable from the command string. They are reported as unresolved, which
  resolves to `ASK` rather than `ALLOW` — but "unresolved" is not "understood".
- **An interpreted program can hide its behaviour.** `python -c` bodies are matched for
  behavioural patterns, not understood, and a script that assembles its command at runtime is
  not visible from its invocation. A binary is judged by its name.
- **A local user can disable a user-level hook.** These are the user's own configuration files.
  The guard raises the cost of an accident and of a steered agent; it is not a control against
  the person at the keyboard.
- **It is not a sandbox and not IAM.** Scoped credentials, read-only roles, network policy, and
  human-controlled execution remain the stronger controls, and the
  [destructive-action policy](destructive-action-safety.md) still requires them.
- **There is a time-of-check/time-of-use gap.** The decision is made against the command as
  written, immediately before execution. A target that changes in that interval is not covered.

## Engineering Tool Capability Framework

See [engineering-tools.md](engineering-tools.md#known-limitations) for the full treatment.

- **The framework resolves transports; it does not authenticate or enforce.** A resolved
  transport means a request can be constructed, not that the far side will accept it, and not
  that the action is permitted — [Execution Guard](execution-guard.md) still gates the command.
- **The `host` transport is not probeable from a script.** Whether the agent host exposes a
  first-class tool is something only the host knows. It is reported as a step to check.
- **MCP detection is presence, not capability.** `tools status` reports that a host MCP config
  mentions a service, the same way access resolution step 1 does. It does not call the server.
- **`reference_status: validated` means the framework path was exercised**, not that every
  capability was integration-tested against a live instance. Tools present only as fixtures
  (`gitlab`, `gcp`, `mysql`, `newrelic`) are labelled and are never counted as supported.
- **Action classification is per capability, not per invocation.** A skill that hand-builds a
  mutating command under a READ capability has misused the framework; the guard is the backstop.

## Evidence and caches

- **Evidence-pack and cache flows depend on the execution environment.** Global, in-repo, ephemeral
  runners, and web agents differ in what they can read, write, or preserve between turns.
- **No warranty or SLA.** This project offers no guaranteed correctness, availability, response time,
  support commitment, or fitness for a particular purpose.

## Memory and evidence

- **Recorded knowledge is evidence, not authority, and the runtime can only enforce shape.**
  `knowledge.py` makes repeated evidence idempotent, disputes a contradicted lesson, and redacts
  every field it writes. It cannot tell whether a locator such as `ABC-123` really supports the
  lesson, or whether two different task keys are two independent observations. A human reviewing
  the pull request that adds the lesson is still the control that matters.
- **A verified definition of done is an auditable claim, not an attestation.** `dod-check`
  refuses a pass without an execution record, a stale revision, a waiver signed by the agent, and
  a boolean schema. It cannot prove the recorded command ran, because the agent that wrote the
  artifact could also have written the log it cites. Protected CI running the same checks on the
  same revision is the stronger boundary; the local artifact makes the claim checkable, not
  unforgeable.
- **The eval corpus validates scenarios, not behaviour.** `run-evals.py` checks that every
  scenario file is well-formed and references real skills. It does not run a model, so a green
  corpus says nothing about whether an agent honours the requirement gate, produces genuine RED
  evidence, or resists an instruction planted in a memory file. Those properties are asserted
  by the deterministic suites where the runtime can hold them and are otherwise documented
  obligations. A release-level behavioural suite with recorded tool trajectories is the item
  named in the roadmap for `1.1`.
- **Symbol spans in a context pack are inferred, not parsed.** `context pack` finds declarations
  by pattern and ends a span at the next declaration at the same or lower indentation, capped
  at 400 lines. Decorators directly above a declaration are included; a span may still end early
  or run into the next symbol, and a `[span-capped]` fragment was cut. The pack says so in its
  notes. Expand the exact target before editing or drawing a conclusion from it.
- **Reversibility is what git can prove, nothing more.** `agent-skills reversibility` sees tracked,
  untracked, ignored, and uncommitted content. It cannot see a backup, a synced folder, a remote
  that has or lacks the commits, or anything that is not a file. `RECOVERABLE` for a commit that
  was never pushed is true only while the local repository survives.
- **`plan-next` reads the evidence pack with a narrow parser.** No YAML library is assumed, so
  `prerequisite_context` reads the documented `delivery_plan.phases[]` shape: scalar keys and block
  lists. Inline flow mappings and multi-line block scalars are skipped rather than guessed at, and a
  prerequisite whose context could not be read is listed under `missing`. The index, not the pack,
  still decides dispatch.
- **The stop-hook fallback needs a task identity.** `finish-task --if-open` recognises the task
  the last `start-task` recorded. Two agents in one repository, or a session that never ran
  `start-task`, give it nothing to close and it records nothing — which is the correct outcome,
  and also means a genuinely abandoned task in that situation leaves no `stopped` record.
