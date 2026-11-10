# Agent Skills subscription terms

**Status: draft.** Written 11 September 2026 as the phase 00 deliverable of the
[commercial plan](../commercial-roadmap.md). It is a starting point for the German counsel review
that phase 00 books, not legal advice and not a published agreement. Every `[BRACKETED]` value is
a fact only the maintainer can supply. Do not link this from a live pricing page before review.

Placeholders used throughout: `[LEGAL NAME]`, `[LEGAL FORM]`, `[ADDRESS]`, `[VAT ID]`,
`[DOMAIN]`, `[EFFECTIVE DATE]`. The version string below changes on every published revision and
is recorded against each customer's acceptance.

Version: `draft-0`.

## 1. Who these terms are between

These terms govern use of the Agent Skills software product ("the Product") between
`[LEGAL NAME]`, `[LEGAL FORM]`, `[ADDRESS]`, Germany ("we", "us") and the person or organisation
that subscribes ("you", "the Customer").

Payment is not made to us directly. Subscriptions are sold through Stripe's Managed Payments
service, under which a Stripe entity is the merchant of record and the seller on your invoice,
and collects and remits applicable VAT, GST, and sales tax. Stripe's own terms govern the payment
transaction. These terms govern the software.

## 2. What a subscription licenses

An active subscription grants each developer holding an assigned seat a non-exclusive,
non-transferable, non-sublicensable right, for the paid period, to:

- install and use the Product on any number of machines that developer personally uses;
- receive every release published during the paid period;
- use the Product on the Customer's own work and on work the Customer performs for its clients;
  and
- receive support as described in section 10.

The Product is licensed, not sold. We retain all intellectual property rights in it.

## 3. Seats

A seat is assigned to one named human being. It is not a concurrency licence, a machine licence,
or a role. Seats may be reassigned between people at any time, free of charge, and reassignment
takes effect immediately.

Local automation acting on behalf of the developer holding the seat — an agent running on that
developer's machine, under that developer's direction — is included in that developer's seat.
Shared continuous-integration runners, service accounts, and unattended automation that is not
directed by a specific licensed developer are not licensed under these terms, and require a
separate written agreement.

Administrative roles that do not use the Product — account owner, administrator, billing manager
— do not require a paid seat.

## 4. What you may not do

You may not:

- allow a person without an assigned seat to use the Product;
- share, publish, resell, sublicense, or redistribute the Product, its source, or any part of it,
  including the skill content and the runtime;
- use the Product to build or train a competing product, or to create a derivative work for
  distribution;
- remove, disable, or circumvent release signature verification, the registry authorisation
  check, or any licence notice;
- share subscription credentials, including CLI tokens, outside the seat they were issued to.

We may suspend access for a breach of this section after notifying you, and may terminate for a
breach that is not remedied within 14 days of that notice.

## 5. Your data and your output

Your source code, prompts, configuration, knowledge bases, and the output the Product generates
remain yours. We claim no ownership or licence over them.

The Product runs on your machines. We do not collect your repositories, your prompts, or your
generated output, and a subscription grants us no right to do so. The account data we do hold is
described in the [privacy notice](privacy.md).

The Product is a tool that produces code and documents. You are responsible for reviewing what it
produces before you use it. We do not warrant that generated output is correct, complete, fit for
any purpose, or free of third-party rights.

## 6. What is not included

A subscription does not include, and its price does not cover: usage of any large language model
or AI API; subscriptions to host editors or agent tools the Product integrates with; your own
infrastructure; or any third-party service the Product can be configured to reach.

## 7. Fees, taxes, and renewal

The price is €11 per assigned seat per month, exclusive of VAT and any other applicable indirect
tax, charged in advance for each monthly period. The amount billed is the seat quantity on your
subscription, not the number of seats you have assigned.

Indirect tax is calculated and added at checkout by the merchant of record, based on your
location and status. Where you supply a valid business tax identifier, the merchant of record
applies the treatment required in your jurisdiction.

Subscriptions renew automatically each month until cancelled. Adding seats takes effect
immediately and the prorated amount appears on your next regular invoice. Reducing seats takes
effect at your next renewal; the current period is not refunded or credited, and you keep the
capacity you paid for until that period ends.

We may change the published price with at least 30 days' notice. A price change does not affect
an existing subscription: you keep the price you subscribed at for as long as that subscription
remains active and uninterrupted.

## 8. Cancellation and refunds

You may cancel at any time from the account portal. Cancellation takes effect at the end of the
period you have paid for, and the portal shows that date and time. We do not refund a partial
month on cancellation.

**30-day money-back guarantee.** If you are not satisfied, email `[SUPPORT EMAIL]` within 30 days
of your first payment and we will refund it in full, without requiring a reason. This applies
once per Customer.

Where you are a consumer in the EU or UK, your statutory right of withdrawal applies in addition
to the guarantee above and is not reduced by it. The merchant of record applies the
consumer-protection requirements of your jurisdiction at checkout.

## 9. Failed payment, suspension, and what happens after

If a renewal payment fails, the payment provider retries it. Coverage you have already paid for
continues until the period it bought has ended. After that, and after cancellation or
termination:

- the registry stops serving new downloads, updates, and release metadata to your seats;
- the copy of the Product already installed on your machines is not disabled, altered, or
  deleted, and we do not delete your files, credentials, or host configuration;
- continued use of the installed Product after your subscription has ended is not licensed under
  section 2, and the remedy for that is renewal.

We do not technically prevent post-expiry use, and we do not represent that we do.

## 10. Support and availability

Support is provided by email at `[SUPPORT EMAIL]`, Monday to Friday, Europe/Berlin business days,
on a best-effort basis, with a target first response within two business days.

We do not offer a service level agreement or an availability guarantee for the account portal or
the release registry at this time. Planned maintenance is announced on the service status page.

## 11. Changes to the Product and to these terms

We may add, change, or remove features. We will not remove a capability that a documented
workflow depends on without at least 30 days' notice.

We may change these terms. Material changes are notified by email at least 30 days before they
take effect, and take effect for you at your next renewal after that date. If you do not accept
them, you may cancel before they take effect.

If we discontinue the Product entirely, we will give at least 90 days' notice, stop charging at
the end of the notice period, and refund any period paid for beyond it.

## 12. Warranties and liability

The Product is provided "as is". To the extent permitted by law, we disclaim all implied
warranties, including merchantability, fitness for a particular purpose, and non-infringement.

Our total liability arising out of or in connection with these terms, whether in contract, tort,
or otherwise, is limited to the fees you paid in the 12 months preceding the event giving rise to
the claim.

Nothing in these terms limits or excludes liability for death or personal injury caused by
negligence, for fraud or fraudulent misrepresentation, for intent or gross negligence, for claims
under the German Product Liability Act, or for any other liability that cannot be limited or
excluded under applicable mandatory law.

## 13. Confidentiality

The Product, its source, its skill content, and any non-public documentation we give you are our
confidential information. You will protect them with at least the care you use for your own
confidential information, and will not disclose them outside the people holding assigned seats.

## 14. Governing law and disputes

These terms are governed by the law of the Federal Republic of Germany, excluding the UN
Convention on Contracts for the International Sale of Goods. Where you are a consumer, this
choice does not deprive you of the protection of mandatory provisions of the law of your country
of residence.

Where you are a business, the place of jurisdiction is `[CITY]`, Germany.

The European Commission provides an online dispute resolution platform at
<https://ec.europa.eu/consumers/odr>. We are not obliged to, and do not, participate in dispute
resolution proceedings before a consumer arbitration board.

## 15. Contact

`[LEGAL NAME]`, `[ADDRESS]`, Germany. Email `[SUPPORT EMAIL]`. VAT identification number
`[VAT ID]`. Full details are in the [imprint](imprint.md).

---

## Review checklist for counsel

The specific questions to put to the reviewing lawyer, so the session is efficient:

- [ ] Is the entity form in section 1 correct, and does it need a commercial register entry?
- [ ] Does the Stripe Managed Payments arrangement leave any German invoicing or VAT obligation
      with us, and does section 1 describe the relationship accurately?
- [ ] Is section 8 compliant with the EU consumer right of withdrawal for digital content, and is
      the immediate-access waiver handled correctly at checkout by the merchant of record?
- [ ] Is the liability cap in section 12 enforceable under German law against businesses and
      against consumers, and are the carve-outs complete?
- [ ] Does section 4 survive AGB review, or does any clause count as a surprising or unreasonably
      disadvantageous term under §§ 305-310 BGB?
- [ ] Is section 9 — no technical enforcement after expiry, use no longer licensed — stated in a
      way that is enforceable and not misleading?
- [ ] Does section 3's exclusion of CI and service accounts need clearer drafting?
- [ ] Is a separate B2B data processing agreement required, and if so is the offer in the privacy
      notice sufficient?
- [ ] Are the notice periods in sections 7 and 11 adequate for a consumer-facing subscription?
