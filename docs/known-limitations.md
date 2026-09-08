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
  that, and rerunning `./setup.init` repairs it.
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

## Evidence and caches

- **Evidence-pack and cache flows depend on the execution environment.** Global, in-repo, ephemeral
  runners, and web agents differ in what they can read, write, or preserve between turns.
- **No warranty or SLA.** This project offers no guaranteed correctness, availability, response time,
  support commitment, or fitness for a particular purpose.
