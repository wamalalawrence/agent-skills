# Agent Skills installer

Install Agent Skills on this machine:

```bash
npx @wamalalawrence/agent-skills install
```

Then open any repository and ask your assistant:

> Use Wamala to investigate this project.

## What this package is

A bootstrap. It checks that the machine can run the installer, then hands over
to the installation engine, which downloads a release, verifies it, stages it,
and activates it. The product itself — the skills, the runtime, the docs — is
not in this package. It arrives from the release source.

That separation is deliberate. A published npm tarball is public permanently,
so nothing protected is ever put inside one.

## After installing

The durable command is `agent-skills`. The npm layer is not needed again.

```bash
agent-skills doctor      # what this environment can actually do
agent-skills verify      # check the installation
agent-skills update      # move to the latest release, transactionally
agent-skills rollback    # return to the previous release
agent-skills uninstall   # remove it again
```

## Optional: Meeting Intelligence

"Listen to this meeting: <link>" turns a Teams, Zoom, or Google Meet meeting into engineering
knowledge. It needs one of three capture methods, which you choose and set up yourself:

| Method | Bot joins | Extra cost | Audio / transcript goes to |
| --- | --- | --- | --- |
| `native` — the platform's own transcript | no | none | stays in your organisation (needs an admin to register an app once) |
| `recall` — a visible Recall.ai bot | yes | ≈ $0.65 per meeting hour, billed by Recall | Recall.ai, in the region you pick |
| `desktop` — record and transcribe locally | no | none | nowhere: your computer only; no one in the meeting is notified automatically, so you tell them |

In every mode your AI assistant extracts the facts, so transcript text reaches its model provider.
Nothing is captured until you pick one:

```bash
agent-skills meeting setup --compare
```

## Requirements

- Python 3.8 or newer
- bash and git
- macOS or Linux. On Windows, use WSL or Git Bash.

## Credentials

Installation asks for none. If the release source is private, the installer
uses the git access you already have — a credential helper, an ssh key, or the
GitHub CLI. That is distribution access; it is never used for your projects and
is never copied into Agent Skills configuration.

Full documentation: <https://github.com/wamalalawrence/agent-skills>
