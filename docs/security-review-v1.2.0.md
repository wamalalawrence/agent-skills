# Security review — v1.2.0

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

`1.2.0` adds Meeting Intelligence. It is the first feature that sends a credential to a third-party
API from the runtime itself, the first that accepts inbound network requests (optionally), and the
first whose primary input is speech from people who never agreed to be an input — so the whole
transcript is untrusted, and so is the model that reads it.

## Scope of this review

- **New:** `scripts/meeting.py`, `meeting_capture.py`, `meeting_recall.py`, `meeting_intel.py`,
  `meeting_store.py`, `meeting_secrets.py`, `meeting_webhook.py`, the `meeting-intelligence` skill.
- **Changed:** `scripts/access.py` (`resolve_access(values_out=…)`), `scripts/knowledge.py`
  (`meetings/` tier), `scripts/context.py` (`window_items`), the instruction-shaped-text pattern in
  `context.py`, `knowledge.py`, and `guard.py`, `scripts/doctor.sh` (Meetings section),
  `bin/agent-skills` (`meeting`).
- No change to the release engine, the installer, Execution Guard's rules or hooks, the shared
  redaction pattern set, or the host adapters.

---

## Threat: the Recall API key leaks

**Probed.** `test-meeting.py`: "Recall statuses map onto the internal lifecycle" (the key goes to
the region host as `Authorization`, and is absent from the storage-host download), "exit codes"
(the key is absent from error output; a base-URL override pointing anywhere but `*.recall.ai` or
loopback is refused).

The key is resolved in-process through the Access Resolver's new `values_out` parameter, so it
never crosses a process boundary, an argv, or stdout; `Resolution` still carries no value and the
`access` CLI never passes the parameter. It is sent only as a header, only to the configured
region host.

**Finding (fixed during this review):** `urllib`'s default redirect handler copies every
non-content header onto the redirected request, `Authorization` included, whatever host the
redirect points at. A redirect from the Recall API would have carried the key elsewhere. The
transport now uses a redirect handler that drops `Authorization` on any cross-host hop and refuses
an https→http downgrade; the test asserts both, and that a same-host redirect keeps the header.

**Finding (fixed during this review):** `doctor` — which `start-task` runs for every task —
resolved the Recall credential to report whether it existed, which read the secret from the
keychain on every task. It now reports presence from profile metadata and environment names
only; a test replaces the secret backend with one that fails if touched.

## Threat: a forged, replayed, or duplicated webhook changes state

**Probed.** "duplicate, out-of-order, stale, and badly signed webhooks are safe": a real listener
on loopback, a valid event accepted once, the duplicate acknowledged and ignored, a stale timestamp,
a bad signature, and an altered body all rejected, and nothing sensitive in the listener's log.

Verification (Svix HMAC-SHA256, `hmac.compare_digest`) runs over the raw bytes before the body is
parsed; timestamps must be within five minutes; event ids are deduplicated for 48 hours. The
design removes the rest of the threat: a verified event only schedules a reconcile, and the
reconciler asks the provider what is true. Every failure returns the same `401`, so the listener
is not a signature oracle. It binds to loopback only; exposure is the user's own tunnel.

**Residual:** without a verification secret there is no listener at all (fail closed); with one,
a party holding the secret can make the machine poll Recall more often. Accepted.

## Threat: spoken content steers extraction

**Probed** (mechanics) and **reasoned about** (the host). Evals 20 and the adversarial run in
`eval-runs/v1.2.0/summary.md`; `test-meeting.py` cases 2, 10, and the mechanical-checks case.

The runtime cannot constrain the host model, so it constrains what the host's output can do:
transcript text reaches the model only inside markers carrying a content-derived nonce, with
marker-shaped text defused before sizing; instruction-shaped lines are flagged; the output must
match a closed schema; a fact whose only evidence is instruction-shaped is dropped; scope comes
from `join`, never from the output; supersession needs explicit replacement wording in cited
evidence. The skill forbids tool use during extraction — **reasoned about**: a host that ignores
its skill can still run tools, and nothing in this runtime can stop that.

**Finding (fixed during this review):** the shared instruction pattern did not match "ignore
**your** previous instructions" or "ignore your instructions", only "ignore (all|any) previous".
The new injection eval found it. The pattern in Context Optimizer, `knowledge doctor`, and
`guard scan-content` was widened together; `test-guard.sh` shows no movement in the
false-positive corpus (116 passed), and "ignore the earlier draft" is deliberately not matched.

**Finding (fixed during this review):** a host could write an instruction-shaped *statement*
backed by innocent evidence, and statements are printed into every later task's preflight. Such
facts are now dropped at `check_fact`, and a test pins it.

## Threat: meeting facts become a steering channel for later agents

**Reasoned about**, partly probed. Facts appear in `knowledge read` in their own section headed as
claims, not verified facts, with an instruction to surface conflicts with code rather than resolve
them. `knowledge doctor` scans meeting files with the same secret and instruction patterns as
lessons. The files are committed, so they arrive through a reviewed pull request like any other
knowledge.

**Residual:** anyone with write access to a repository can author a meeting file for that
repository's own scope, exactly as they can author a lesson. The scope check stops it crossing
into another repository; review is the control inside one.

## Threat: a secret said in a meeting is stored

**Probed.** Case 10 (a spoken password, letters spelled out, a connection string read aloud, a
value announced in one utterance and said in the next, a token split across three utterances)
asserts none of them appear in the stored transcript, window checkpoints, the committed facts, the
record, or any command output; the mutation probe removes the spoken layer and the password
reaches storage.

**Finding (fixed during development):** the split-token case first leaked the token's tail, and
window checkpoints briefly stored facts before the fact-level redaction pass ran. Both are fixed
and covered by case 10.

**Residual:** detection is heuristic. A secret spoken in an unusual shape can pass. The posture is
to redact when uncertain, at the cost of occasional over-redaction.

## Threat: facts leak across scopes

**Probed.** Case 11 and the scope mutation probe: facts from repository A are absent from B's
recall, a file copied from A into B is withheld, writing A's payload into B is refused, and
`team:`/`org:`/`project:` scopes are refused rather than widened. Unscoped meetings stay
`PENDING_REVIEW` in local state until the user accepts them into a repository.

## Threat: covert or unconsented recording

**Reasoned about**, with the CLI half **probed**. `join` refuses (exit `2`, nothing created) until
the one-time notice is acknowledged; the bot name and the chat notice can be changed but never
emptied; retention is always sent. Whether an agent passes `--acknowledge-recording-notice`
without asking is host behaviour, governed by the skill and the capture eval — the runtime cannot
distinguish a user's yes from an agent's.

## Threat: meeting links and local state disclose more than they should

**Probed.** Case 1 asserts a Zoom passcode (`pwd=`) is never stored; records and transcripts are
written `0600` in `0700` directories (case 13 checks the mode).

## Threat: the transcript download URL is used to reach something else

**Reasoned about.** The adapter fetches whatever https URL Recall returns as the transcript's
download location, without credentials, capped at 50 MB, and parses it as JSON only. A
compromised provider could point it at another https host reachable from the user's machine.
**Residual,** accepted: the provider already sees the meeting itself.

## Threat: update or rollback corrupts meeting state

**Probed.** `test-cli-install.sh` asserts a record survives update and rollback byte-for-byte;
`test-release-readiness.sh` rolls back to the previous tag and runs its `verify` and `doctor`
against meeting state; case 13 asserts an unknown schema is reported, not rewritten.

## A development incident worth recording

Before the offline guard existed, one run of the exit-code case sent a single request to Recall's
`us-east-1` host carrying the placeholder key `test-key-not-real`, because
`AGENT_SKILLS_RECALL_REGION` doubled as both a config override and the Access Resolver's
environment name. No real credential was involved. The config override was removed and every
test case now pins the Recall base URL to a closed loopback port, so a case that forgets its fake
fails instead of reaching the network.

## Residual risks and their controls

| Risk | Control | Why it is not the default |
| --- | --- | --- |
| Heuristic spoken-secret detection misses a shape | `inspect --purge` and review of the committed file | No detector is complete; stricter rules would destroy ordinary speech |
| A host ignores its skill and uses tools during extraction | Host permission settings | Outside what a CLI can enforce |
| Provider-supplied download URL | Provider trust | The provider already processes the meeting |
| Recall keeps metadata and logs after media deletion | Documented in the user guide | Outside Agent Skills' control |
