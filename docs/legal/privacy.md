# Agent Skills privacy notice

**Status: draft.** Written 11 September 2026 as the phase 00 deliverable of the
[commercial plan](../commercial-roadmap.md). It is a starting point for the German counsel review
that phase 00 books, not legal advice and not a published notice. Every `[BRACKETED]` value is a
fact only the maintainer can supply.

Version: `draft-0`.

## 1. Who is responsible

The controller for the processing described here is `[LEGAL NAME]`, `[ADDRESS]`, Germany, email
`[PRIVACY EMAIL]`. We have not appointed a data protection officer; the size and nature of this
processing does not require one under Art. 37 GDPR, and the counsel review confirms that.

This notice covers the account portal at `[DOMAIN]` and the release registry the Agent Skills CLI
talks to. It does not cover the Product running on your own machine, which is described in
section 6.

## 2. What we hold, why, and on what legal basis

| Data | Why we hold it | Legal basis | Kept for |
| --- | --- | --- | --- |
| Email address, display name, and the identifier from your GitHub sign-in | To create and authenticate your account | Art. 6(1)(b) — performance of the contract | Life of the account, then 30 days |
| Billing account name, membership, and role | To determine who may administer seats and billing | Art. 6(1)(b) | Life of the account, then 30 days |
| Seat assignment history: who assigned or revoked, and when | To enforce the licence and answer billing disputes | Art. 6(1)(b), and 6(1)(f) for audit | 180 days after close |
| Stripe customer, subscription, and invoice identifiers | To link your account to the subscription that pays for it | Art. 6(1)(b) | Life of the account, then as required by tax law |
| CLI device records: label, created, last used, last country | To let you revoke sessions and detect credential sharing | Art. 6(1)(b), and 6(1)(f) for licence abuse | Until revoked, then 180 days |
| Invitation records: invited address, inviter, outcome | To operate invitations and show administrators what they sent | Art. 6(1)(b) | 180 days after acceptance, revocation, or expiry |
| Server logs: path, status, timing, correlation ID, truncated IP | To operate the service, investigate faults, and rate-limit abuse | Art. 6(1)(f), for a working and defensible service | 30 days |
| Security audit events: which account did which administrative action, and when | To investigate account compromise and licence abuse | Art. 6(1)(f) | 180 days |
| Support email correspondence | To answer you | Art. 6(1)(b) and 6(1)(f) | 24 months |

We do not hold your payment card, bank details, or billing address. Those go to the merchant of
record and never reach our systems.

We do not use your data for profiling, automated decision-making with legal effect, advertising,
or any purpose other than those listed. There is no marketing list. Account email is not
marketing consent.

## 3. Who processes it on our behalf

| Processor | What it handles | Where |
| --- | --- | --- |
| Cloudflare, Inc. | Application hosting, static assets, release object storage, edge request handling and logs | Global edge; release objects in the EU |
| Neon, Inc. | The account database | EU Central |
| Resend (Plus Five Five, Inc.) | Transactional email: sign-in codes, invitations, account notices | United States |
| GitHub, Inc. (Microsoft) | Source control, CI, and the GitHub sign-in option | United States |
| Better Stack | Uptime monitoring of public endpoints; no personal data | EU |

Stripe is not a processor for this purpose. Under Managed Payments, a Stripe entity is the
merchant of record and an independent controller of the payment transaction, including the
payment method, billing address, and tax status you give it at checkout. Stripe's own privacy
notice governs that, and Stripe may contact you directly about a payment or a subscription.

Transfers to processors outside the EU rely on the European Commission's standard contractual
clauses, and where applicable on the EU-US Data Privacy Framework. The data processing agreement
with each processor is on file. A current list is maintained; we give 30 days' notice before
adding a processor that handles personal data.

## 4. Business customers and data processing agreements

If you are a business customer and require a data processing agreement for the personal data of
your developers that we hold as part of your account, email `[PRIVACY EMAIL]` and we will provide
one.

## 5. Your rights

You have the right to access your data, to correct it, to have it erased, to restrict or object
to its processing, and to receive it in a portable format. Email `[PRIVACY EMAIL]` and we will
respond within one month.

You can exercise most of these directly in the portal: view and edit your profile, see and revoke
every CLI device, see your memberships, download your account data, and delete your account.

Deleting your account removes your profile and your devices. It does not cancel a subscription
your organisation pays for, and it does not delete invoice records that tax law requires the
merchant of record to retain. Where we must keep a record for a legal obligation, we restrict it
to that purpose rather than continuing to use it.

You may complain to a supervisory authority. Ours is the `[SUPERVISORY AUTHORITY]`.

## 6. What the Product does on your machine

The Product runs locally. It reads and writes files in the repositories you point it at, and
stores its own configuration, memory, and knowledge base on your machine.

- We collect no telemetry. There is no usage reporting, no crash reporting, and no analytics.
- Your source code, prompts, and generated output never reach our servers.
- The only network requests the Product makes to us are: sign-in, checking your licence status,
  fetching release metadata, and downloading a release. Each carries your CLI token and nothing
  about your work.
- Your CLI token is stored in `~/.config/agent-skills/credentials.json` with owner-only
  permissions. Deleting that file, or running `agent-skills logout`, removes it.

If we ever add optional diagnostics, they will be off by default, will say exactly what they
send, and will require your explicit consent.

## 7. Cookies

The portal sets one essential cookie, which holds your sign-in session. It is required for the
portal to work and is not used for tracking. There are no analytics cookies, no advertising
cookies, and no third-party trackers, so there is no consent banner.

The checkout page is operated by the merchant of record and sets its own cookies under its own
notice.

## 8. Security

Transport is encrypted. Passwords are not used; sign-in is by GitHub OAuth or a one-time email
code. CLI tokens and invitation tokens are stored only as hashes and cannot be recovered from our
database. Tokens, codes, email addresses, and billing details are excluded from application logs.
Access to production data is limited to the maintainer and is audited.

We will notify affected users and the supervisory authority of a personal data breach within the
timescales Art. 33 and 34 GDPR require.

## 9. Changes

Material changes are notified by email at least 30 days before they take effect. The version
string at the top of this notice changes with every revision.

---

## Review checklist for counsel

- [ ] Is a data protection officer required at this scale, and is section 1 correct?
- [ ] Is the controller/controller characterisation of Stripe under Managed Payments correct, and
      is section 3 worded so that we do not accidentally claim to be its processor?
- [ ] Are the legal bases in section 2 correct, particularly the legitimate-interest entries for
      audit trail, device country, and rate limiting — and is a balancing test needed on file?
- [ ] Is retaining the last-used country of a CLI device proportionate for licence-abuse
      detection, and does it need to be in the terms as well?
- [ ] Is the single essential session cookie genuinely exempt from consent under German TDDDG?
- [ ] Which supervisory authority applies, given the maintainer's registered address?
- [ ] Is the DPA offer in section 4 sufficient, or should a standard DPA be published?
- [ ] Are the retention periods defensible, especially 180 days for audit and seat history?
