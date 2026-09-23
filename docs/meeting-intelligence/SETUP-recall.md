# Recall capture

A visible bot named "Agent Skills Meeting Assistant" joins the meeting, posts a recording notice in
chat, and Recall.ai records and transcribes it. It works for any Teams, Meet, or Zoom meeting,
including other organisations'. Recall is a third party that processes every participant's voice
on your behalf: read [PRIVACY.md](PRIVACY.md) before your organisation adopts it.

## Cost

Billed by Recall to the account **you** open: about **$0.50 per hour** of recording plus **$0.15
per hour** of Recall transcription, ≈ **$0.65 per meeting hour**. The first hours after signup are
free. Last verified on **2026-09-23** (recall.ai/pricing). `join` prints the rate from
`recall.cost_per_hour_usd` in `~/.config/agent-skills/meeting.json` (default `0.65`).

## Setup

```bash
agent-skills meeting setup recall
```

Run it yourself in a terminal. It walks through:

1. **Account.** Sign up at recall.ai (pay as you go).
2. **Region.** Recall runs one deployment per region, and a key, its bots, and their recordings
   live in one region only: `us-west-2`, `us-east-1`, `eu-central-1`, `ap-northeast-1`. Setup
   suggests `eu-central-1` when your timezone or locale is in the EU; **choose `eu-central-1` for
   EU organisations** so recordings stay in the EU. `--region` sets it non-interactively.
3. **API key.** Create it in the Recall dashboard *for that region*, then paste it at the hidden
   prompt. It goes to your OS keychain (or a `0600` file under `~/.config/agent-skills/secrets/`),
   never to a config file, a log, or a process argument.
4. **Verification secret** (optional). Only needed for the webhook listener
   (`meeting status --listen`); polling works without it.
5. **Self-test.** One authenticated read (`GET /api/v1/bot/?page_size=1`) in your region proves
   the key and region match. **No bot is created.** A key from another region is reported as
   rejected.
6. **Notice.** The cost, data-flow, and consent notice; type `yes` to accept it. Recall becomes
   your default unless you pass `--no-default`.

Re-running is safe: a stored key and an accepted notice are detected and skipped. The key can
also come from `AGENT_SKILLS_RECALL_API_KEY` / `AGENT_SKILLS_RECALL_REGION`, or be stored with
`agent-skills access set --profile recall --service recall --field region=<region> --secret-field api_key`.

## Using it

```bash
agent-skills meeting join <link> [--via recall]
```

The first join shows the one-time recording notice. `join` refuses to start a second bot for a
meeting link that already has an active Recall meeting on this machine. Everything else — the
visible name, the chat notice, media retention (48 h, deleted once the transcript is stored), the
lifecycle — is unchanged from `1.2.0`; see [meeting-intelligence.md](../meeting-intelligence.md).
