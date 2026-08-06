# 27 — Security, Privacy, and Outreach Compliance Safeguards

**Specification version:** 2.1  
**Primary owner:** Security and governance

## Purpose

Define application security, SSRF and prompt-injection defenses, secret handling, contact-data minimization, retention, suppression, audit, and human/legal gates for outreach.

This document defines technical safeguards, not a final legal determination for a country, recipient, or campaign. Obtain qualified legal review before scaled outbound activity.

## Access control

Roles:

```text
admin
founder
researcher
reviewer
viewer
```

- All application pages require authentication except explicitly minimal health/webhook endpoints.
- Enforce authorization in both views and domain services.
- Founder/reviewer permission is required for opportunity/solution/target/draft approval.
- Knowledge activation, exports, suppression removal, and configuration changes require elevated permission.
- Use Argon2 as the preferred password hasher when available.
- Consider MFA/SSO before hosting sensitive team/client data.

## Django production security

- HTTPS and secure/HTTP-only/SameSite cookies.
- CSRF protection for all state-changing requests, including HTMX headers/forms.
- strict allowed hosts and trusted origins;
- clickjacking protection;
- HSTS only after HTTPS is verified;
- debug off;
- content security policy through a maintained Django 5.2-compatible package/middleware, with an upgrade path to Django's native CSP in a future supported release;
- safe file/download headers;
- no raw provider exception pages.

## Secret handling

- Local `.env` is ignored.
- Production supports Compose secrets/secret manager through `*_FILE`.
- Secrets never enter Docker build args, images, prompts, Celery payloads, database rows, logs, or error pages.
- Rotate provider/webhook/Django/database secrets through documented runbooks.
- Contact-route encryption and normalized HMAC use separate keys loaded through the secret provider; key identifiers/rotation metadata are stored, keys are not.
- Restrict secrets to services that need them; for example, fetch workers do not need email-provider credentials.

## Safe fetching and SSRF

- Only HTTP/HTTPS and allowed ports.
- Validate host and every resolved IP before connection.
- Reject loopback/private/link-local/multicast/reserved/metadata destinations.
- Revalidate every redirect; preferably disable or tightly bound redirects.
- Protect against DNS rebinding/TOCTOU through resolved-IP pinning or server egress proxy/firewall.
- Bound response size/time/content type and per-domain concurrency.
- No `file:`, `ftp:`, `gopher:`, internal Docker hostnames, or cloud metadata.
- Never render raw fetched HTML. Escape text; sanitize only when formatted excerpts are required.

## Prompt injection and data exfiltration

- Untrusted web/job/email text only in user data messages.
- Never interpolate untrusted content into developer instructions.
- Structured outputs and enum/source validation constrain downstream flow.
- Public web research has no private FTL knowledge, contacts, or CRM tool access.
- Private matching/solution design has no web tool.
- Dedicated deep research receives only public context and read-only research tools.
- Incoming email classification cannot call tools or change state.
- Models never receive API keys, auth headers, suppression exports, or unrelated records.
- Add adversarial fixtures for prompt injection, data exfiltration, false citations, and malicious URLs.

## Contact data minimization

Collect only what is needed:

```text
professional name if publicly relevant
current professional role/department
company
public business contact route
source URL and retrieval date
route origin and provenance; observation, freshness, deliverability, and outreach-eligibility states
communication and suppression history
jurisdiction/legal-review metadata
```

Do not collect private email, home address, private phone, sensitive characteristics, unrelated social profiles, or hidden profile data. Do not bypass login/access restrictions. Public-source extraction cannot infer a warm introduction, existing relationship, or event connection; those routes require authorized human entry and provenance.

## Contact-purpose metadata

For each selected route, preserve:

```text
contact_purpose
source_url
retrieved_at
jurisdiction
legal_review_status
lawful_basis_note nullable
retention_policy
```

`lawful_basis_note` is documentation, not an automated legal conclusion.

## Outreach gate

The platform MUST NOT assume cold email is lawful merely because a business address is public. German §7 UWG and applicable European/national electronic-communications and data-protection rules require route-specific review. The product therefore:

- never auto-sends first contact initially;
- supports public routes and human-origin warm-introduction/existing-relationship/event routes as distinct provenance classes;
- requires a human to select route/recipient/message;
- can require legal review by route/jurisdiction;
- records public source evidence or authorized human-origin provenance and purpose;
- includes a permanent suppression system;
- stops immediately on objection/unsubscribe;
- supports data export/deletion workflows subject to record-retention obligations.

## Suppression

Check suppression:

1. before target selection;
2. before packet creation;
3. before approval;
4. immediately before external provider draft/send action.

An unsubscribe/objection creates suppression immediately. Only a privileged human can remove it, with reason and audit. The model cannot remove it.

## Retention

Define versioned retention classes for:

- temporary fetch bodies;
- source evidence;
- rejected discovery candidates;
- research reports/provider responses;
- stale contact observations;
- interactions;
- provider logs;
- backups;
- suppression/legal records.

Use scheduled deletion through services with audit, legal-hold support, and dry-run reporting. Do not keep raw web/email bodies indefinitely by default.

## Exports and deletion

- Elevated permission and reason required.
- Export is generated asynchronously, encrypted/access-controlled where appropriate, time-limited, and audited.
- Deletion/anonymization respects related audit/suppression/legal records and uses a documented policy rather than ad hoc cascading.

## Acceptance criteria

- Auth, permissions, CSRF/HTMX, secure cookies, and deployment checks are tested.
- SSRF tests cover redirects, IPv4/IPv6 private ranges, DNS rebinding simulation, and metadata endpoints.
- Prompt-injection fixtures cannot alter instructions or access private context.
- Suppressed routes cannot be packeted, approved, or externally actioned.
- Public research contains no private knowledge.
- Export and suppression removal require elevated permission/audit.
- Scaled outbound remains blocked until legal policy is explicitly configured and reviewed.
