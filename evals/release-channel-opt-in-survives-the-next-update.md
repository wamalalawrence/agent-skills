# Eval — Opting into release candidates has to survive the next update

A maintainer published `1.0.0-rc.2`, installed it on their own machine to test it, and later ran
`agent-skills update`. They got `0.44.0` — the stable release — and had to ask whether something
had gone wrong. Nothing had gone wrong with that command. The machine had been installed on the
`stable` line, and `stable` correctly never offers a pre-release.

What went wrong was everything after they fixed it. Once the machine *was* on `rc`, a bare
`agent-skills check-updates` reported `ahead`, a bare `agent-skills update` proposed moving them
backwards onto the stable release, and `check-updates --channel rc` printed an `apply:` line
naming a command that would not perform the update it had just described.

The person who hit this is the person who publishes the candidates. If the release line is this
hard to stay on for them, nobody else is on it either, and a release candidate with no testers is
a stable release with extra steps.

## Setup

A release source publishing, in order: `2.0.0-rc.1`, `2.0.0-rc.2`, `2.0.0`, `2.0.1-rc.1`.

Two machines:

- **R** — installed with `--channel rc` at `2.0.0-rc.1`. A tester.
- **S** — installed with `--channel stable` at `2.0.0`. Everyone else.

Every command below is typed without `--channel`, the way someone types it when they are not
thinking about channels, which is most of the time.

## Skill Under Test

`software-engineer`, `issue-investigator`

The subject is the release lifecycle CLI — install, update, check-updates, rollback, doctor —
which is what these two skills investigate and change when a report like this arrives.

## Expected Behavior

**R is offered `2.0.0-rc.2`.** `check-updates` says an update is available and names it. It does
not say `ahead`. The `apply:` line is a command that, run verbatim, performs that update — and
`update` with no flags performs it.

**R takes `2.0.0` when it appears**, because `rc` is a superset and a tester must receive the
release that supersedes their candidate. **R is still on the `rc` line afterwards**, and is
offered `2.0.1-rc.1`. This is the case the whole design turns on: installing a stable release is
not a decision to stop testing candidates.

**S is offered nothing**, and no candidate is named anywhere in its output. When S deliberately
asks — `check-updates --channel rc` — it is told about `2.0.1-rc.1`, and the `apply:` line
carries `--channel rc`, because on S a bare `update` would resolve `stable`. Running that printed
line puts S on the rc line, and S stays there.

**Rollback does not change anyone's line.** It chooses a version, not a channel.

**A machine that has never chosen follows `stable`**, and so does one whose manifest holds
something that is not a channel. The narrow line is what you fall back to when you do not know.

`agent-skills doctor` can answer "which line am I on" without the user reading a JSON file.

## Pass/Fail Checklist

- [ ] R's bare `check-updates` offers `2.0.0-rc.2` and never reports `ahead`.
- [ ] R's bare `update` installs `2.0.0-rc.2`.
- [ ] Every `apply:` line, run verbatim, performs the update it described.
- [ ] R installs `2.0.0` under the superset rule.
- [ ] R is offered `2.0.1-rc.1` after installing `2.0.0`.
- [ ] S is never offered a candidate and never has one named in its output.
- [ ] S can opt in, and the opt-in is typed once.
- [ ] Rollback leaves the followed line unchanged.
- [ ] A manifest containing a non-channel value resolves to `stable`.
- [ ] An install made before the followed line was recorded still resolves `rc`.
- [ ] `doctor` reports the line the machine follows.

## Must Not Do

- Require `--channel rc` on every command. A flag that must be re-typed to preserve a decision is
  not a decision, and the failure mode is silent: the machine reports that it is up to date.
- Resolve the channel from the version that happens to be installed. That is the same conflation
  that dropped R off the line, wearing a different hat.
- Print an `apply:` hint that omits a flag the check itself needed. A command that does not do
  what the line above it said teaches people to stop reading the output.
- Offer a pre-release to a machine that never asked for one, for any reason, including a manifest
  that says so in a way the code does not recognise.
- Propose `--allow-downgrade` as the way out. It is the correct guard reporting an incorrect
  resolution; forcing past it moves a tester backwards off the line they are testing.
- Fix this by changing what `stable` means.

## Why This Scenario

Because the first command in it was working correctly and the report was still real. `update`
returning `0.44.0` to a stable machine is the contract being honoured, and it is also a maintainer
unable to reach their own release candidate. The defect was not where the complaint pointed, and
finding it meant asking what happened *after* the obvious answer was given.

The S cases are here in equal weight because the fix widens a channel, and anything that widens a
channel has to be tested from the side where widening would be a defect.
