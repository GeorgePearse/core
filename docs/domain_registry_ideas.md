# Domain registry ideas

Research captured on **6 October 2026**, at George Pearse's request.
This is a record of product and business hypotheses, not an application, an
availability guarantee, or a valuation. Dates and registry status below are a
snapshot and must be checked again before acting.

## The opportunity

Operate a useful public domain ending and earn recurring registration and renewal
revenue from names underneath it. For example, an operator of `.api` could support
names such as `weather.api` and `payments.api`. These examples illustrate the idea;
they are not claims about ownership or availability.

The strongest initial hypotheses are **`.api` for durability**, **`.agent` for
upside**, and **`.code` for broad developer appeal**. A lasting category, many
potential customers, and a credible route to distribution matter more than a
clever word alone.

## Candidate shortlist

The ranking is qualitative judgment from the discussion, not measured market demand.
All six were absent from the [IANA delegated TLD list][iana-list] when checked on
6 October 2026. **Absent from the root does not mean available to apply for:**
pending applications, reserved names, objections, or other restrictions can still
prevent an application or delegation.

| Ending | Commercial hypothesis | Illustrative uses | Main weakness |
| --- | --- | --- | --- |
| `.agent` | AI products plus established travel, property, insurance, and talent agents give it several potential customer groups. | `coding.agent`, `travel.agent` | AI demand could be speculative; competing applicants and singular/plural alternatives need investigation. |
| `.api` | Short, precise, and useful across software businesses; the underlying category may outlast particular AI architectures. | `weather.api`, `payments.api` | Developers already have inexpensive `api.company.com` subdomains. A new ending needs a reason to switch. |
| `.code` | Software products, education, portfolios, and open-source projects offer a broad audience. | `learn.code`, `review.code` | Competes with established `.dev` and `.app`. |
| `.robot` | A memorable identity for robotics companies, products, and services. | `warehouse.robot`, `inspection.robot` | Smaller immediate customer base and uncertainty about adoption. |
| `.compute` | Cloud infrastructure, GPU providers, and research platforms may value specialist branding. | `rent.compute`, `research.compute` | Potentially valuable customers but fewer registrations; customer budgets do not automatically imply willingness to pay for a domain. |
| `.wallet` | Payments, identity, and digital assets provide product branding opportunities. | `personal.wallet`, `business.wallet` | Fraud, abuse, and reputation management could be expensive. |

Adjacent brainstorming candidates to screen, rather than priority recommendations:
`.agents`, `.payments`, `.auth`, `.verify`, `.verified`, `.gpu`, `.robots`,
`.robotics`, `.llm`, `.model`, `.models`, and `.proof`. These also did not appear in
the checked root list. Their application eligibility and demand remain unverified.
Short-lived technical terminology such as `.llm` could age worse than a broader
category such as `.code`.

Already delegated reference points include `.ai`, `.app`, `.cloud`, `.dev`,
`.data`, `.id`, `.pay`, `.buy`, `.shop`, `.store`, `.health`, `.secure`, `.homes`,
`.jobs`, `.work`, `.chat`, `.search`, `.review`, `.reviews`, `.build`, `.run`,
`.tools`, `.software`, `.trust`, `.finance`, `.insurance`, `.med`, and `.care`.
Their existence is useful competitive context, not evidence that their registries
are available for acquisition. See the [live IANA list][iana-list].

## Product and distribution ideas

- Offer the ending during project creation in hosting platforms, developer tools,
  API platforms, or relevant industry software. Test partner interest before
  treating distribution as solved.
- Make registration, DNS setup, and hosting connection straightforward. The ending
  itself supplies naming, not automatic API discovery, AI capabilities, or trust.
- Investigate whether buyers want a company identity, a product identity, or a
  service endpoint; those uses imply different volumes and renewal behavior.
- Validate willingness to renew at the normal price, not just discounted first-year
  registrations. Model registry revenue separately from the registrar's retail price.
- Compare a standalone registry with a product built on a normal registered domain.
  A product and its subdomains can be tested without operating an entire TLD.

## How a public ending works

A TLD exists as a delegation in the public DNS root. Ignoring caches, a recursive
resolver asks the root servers who handles `.review`, asks the `.review` servers
who handles `pulls.review`, and then asks that domain's authoritative servers for
its address records. Browsers do not need a new hardcoded list of endings each time
one is delegated. Root DNS is served by distributed infrastructure; resolvers can
bootstrap from a root hints file. [IANA root-server explanation][root-servers].

`pulls.review`, the example that prompted this discussion, is a normal domain under
`.review`; its site describes a GitHub pull-request review tool. The `.review`
registry is sponsored by dot Review Limited and was delegated in 2015.
Sources: [pulls.review][pulls], [IANA `.review` delegation][review].

The proposed personal example `.george` is **already delegated to Wal-Mart Stores,
Inc.**, so it is not a new string George can simply create. See the
[IANA `.george` record][george]. A private DNS override can make custom names work
for configured users, but does not give them normal public DNS reachability.

## Public-registry application constraints

Under the 2026 program:

1. Apply as an established eligible legal entity. Individuals and sole
   proprietorships are not eligible.
2. The standard evaluation fee is **USD 227,000 per application**, with specified
   support/variant exceptions and possible conditional fees. This is an evaluation
   fee, not the total budget and not a guarantee of approval.
3. Use an evaluated Registry Service Provider for the technical registry functions.
   Budget separately for operations, compliance, professional advice, distribution,
   and any contention process.
4. Pass the applicable evaluations, resolve objections or competing applications,
   execute the registry agreement, and proceed through delegation.

Sources: [Applicant Journey][journey] and [ICANN program overview][program].
Applications for closed generic endings operated exclusively for the operator and
its affiliates are currently not permitted. A generic registry business therefore
cannot assume that it can reserve the whole category solely for itself.
[ICANN closed-generics explanation][closed-generics].

## Dated application milestones

- **12 August 2026:** the 2026 application window closed. A new application cannot
  now be submitted to that round. [Closure announcement][closed].
- **7 October 2026, 18:00 UTC:** announced Reveal Day, when ICANN will publish the
  applications proceeding through the program, including primary and applicable
  replacement strings, applicants, and contention sets.
- **8–21 October 2026:** announced replacement period for eligible existing applicants.
- **17 November 2026:** announced String Confirmation Day.

The latter three dates come from [ICANN's 29 September announcement][reveal].
They are recorded as announced milestones, not as events already verified to have
happened. This note does not assume any of the shortlisted strings is uncontested.

## Questions for a commercial assessment

1. Which candidates were applied for in 2026, by whom, and with what contention?
   Recheck after both Reveal Day and String Confirmation Day.
2. Is the string permitted and distinguishable from existing or competing strings?
3. Who would register it, how many of them exist, and why would they renew instead
   of using an existing TLD or subdomain?
4. Which registrar, hosting, or vertical-software partners would distribute it?
5. What are the actual wholesale revenue, renewal, operating-cost, and customer
   acquisition assumptions? Avoid deriving a valuation from word appeal alone.
6. Would an existing registry partnership or a normal-domain product validate the
   demand more cheaply before considering a future application round?

No applications, purchases, outreach, or monitoring schedules are created by this
research note.

[iana-list]: https://data.iana.org/TLD/tlds-alpha-by-domain.txt
[root-servers]: https://www.iana.org/domains/root/servers
[pulls]: https://pulls.review/
[review]: https://www.iana.org/domains/root/db/review.html
[george]: https://www.iana.org/domains/root/db/george.html
[journey]: https://newgtldprogram-2026-agb.icann.org/en/5-module-1-the-applicant-journey.html
[program]: https://newgtldprogram.icann.org/en
[closed-generics]: https://newgtldprogram.icann.org/en/application-rounds/round2/2026-round-general/application-types/faqs/non-permitted-strings/what-are-closed-generics
[closed]: https://www.icann.org/en/announcements/details/icann-2026-round-closes-with-more-than-1600-new-gtld-applications-13-08-2026-en
[reveal]: https://www.icann.org/en/announcements/details/icann-announces-date-for-reveal-day-and-other-2026-round-milestones-29-09-2026-en
