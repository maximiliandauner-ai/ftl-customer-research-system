# 16 — Buyer Roles, Contact Persons, Routes, and Verification

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Opportunity operations  
**Canonical prompts:** `buyer_role_inference`, `contact_route_extractor` version `2.1.0`

## 1. Purpose

Identify the role categories that could own an approved FTL solution, preserve source-backed public person/role observations, discover legitimate public contact routes, support human-origin routes such as warm introductions, and keep observation, freshness, deliverability, outreach eligibility, and suppression separate.

The system does not guess email addresses, scrape gated networks, or treat a public address as permission to contact.

## 2. Preconditions and order

```text
current research claims
    -> approved/current SolutionHypothesisV2
    -> current AssetMatchResultV2 (including an explicit zero-asset result)
    -> BuyerRoleResultV2
    -> deterministic/public person and route discovery
    -> human target and route selection
    -> packet builder
```

Research may contain `organizational_ownership` claims, but it does not create final buyer-role hypotheses. Buyer roles are inferred in relation to the proposed engagement.

## 3. Domain concepts

### 3.1 BuyerRoleHypothesis

A role category, not a person.

Examples:

```text
economic_owner
operational_owner
technical_owner
creative_owner
learning_owner
procurement_or_legal_influencer
executive_sponsor
unknown
```

A hypothesis stores the role label/key, owner type, responsibility match, priority, confidence, source/claim/evidence references, solution version, and unknowns.

### 3.2 ContactPerson

A durable professional identity observed publicly or entered by an authorized human. A person record does not itself assert a current role, employer, or usable route.

### 3.3 ContactObservation / ContactRoleHistory

A source-backed or human-confirmed observation that a person held/holds a role at a company. Historical observations remain immutable.

### 3.4 ContactRoute

A possible communication route. Route existence, provenance, freshness, deliverability, eligibility, and recommendation are independent.

## 4. Buyer-role inference

Input:

```text
approved solution ID/version
buyer_role_requirements from the solution
company structure and organizational-ownership claims
selected signal evidence
configured role ontology
```

The model:

- returns role categories only;
- does not create names, emails, reporting lines, or contact routes;
- distinguishes economic, operational, technical, creative, and influencing ownership;
- references only supplied source/claim/evidence IDs;
- uses `unknown` where ownership cannot be supported;
- may propose several role hypotheses with explicit priority/confidence.

## 5. Person discovery

Person discovery is primarily deterministic and source-backed:

- official company team/leadership/department pages;
- official author biographies and event pages;
- official press releases;
- persisted public professional profile URLs where access is allowed;
- authorized human entry.

Do not bypass login, access controls, robots/policy restrictions, or private-profile settings. A model may extract a name/title from already persisted allowed text only through a strict schema; Python validates the exact evidence span and source.

## 6. Route origins

```text
public_source
human_entered
existing_relationship
event
```

### Public-source routes

The automated route extractor may return only:

```text
role_email
individual_business_email
contact_form
professional_profile
phone
other_public_route
```

Every route must be explicitly present in supplied persisted source material and reference registered source/evidence IDs.

### Human-origin routes

Only an authorized user/service may create:

```text
warm_introduction
existing_relationship
event_connection
```

These require `created_by_user_id` and a provenance note or relationship/event reference. The public-source extractor may never infer them.

## 7. ContactRouteResultV2

```json
{
  "schema_version": "2.1",
  "prompt_version": "2.1.0",
  "routes": [
    {
      "route_type": "contact_form",
      "route_origin": "public_source",
      "value": "https://example.com/contact",
      "contact_person_id": null,
      "buyer_role_key": "head_of_learning_and_development",
      "observation_status": "published_officially",
      "freshness_status": "current",
      "deliverability_status": "unknown",
      "outreach_eligibility": "unreviewed",
      "source_ids": ["SRC-000004"],
      "evidence_ids": ["EV-000010"],
      "retrieved_at": "2026-08-05T08:00:00Z",
      "confidence": 0.99
    }
  ],
  "unknowns": [],
  "review_flags": []
}
```

The extractor never sets eligibility to approved and never labels a published address as delivered/verified.

## 8. Stored ContactRoute

```json
{
  "company_id": "uuid",
  "contact_person_id": null,
  "buyer_role_hypothesis_id": "uuid",
  "route_type": "contact_form",
  "route_origin": "public_source",
  "value": "https://example.com/contact",
  "primary_source_id": "SRC-000004",
  "source_ids": ["SRC-000004"],
  "evidence_ids": ["EV-000010"],
  "created_by_user_id": null,
  "provenance_note": null,
  "retrieved_at": "2026-08-05T08:00:00Z",
  "last_checked_at": "2026-08-05T08:00:00Z",
  "observation_status": "published_officially",
  "freshness_status": "current",
  "deliverability_status": "unknown",
  "outreach_eligibility": "unreviewed",
  "confidence": 0.99,
  "status": "active",
  "row_version": 1
}
```

Email/phone values are encrypted according to security policy. A separate keyed HMAC supports deduplication and suppression without exposing plaintext.

## 9. Independent route states

### Observation status

```text
published_officially
published_third_party
human_confirmed
unconfirmed
disputed
```

### Freshness status

```text
current
stale
unknown
```

### Deliverability status

```text
unknown
delivered
replied
bounced
invalid
```

Deliverability changes only from actual provider/delivery/interaction evidence or an authorized verification process. Publication alone leaves it `unknown`.

### Outreach eligibility

```text
unreviewed
eligible_after_human_review
blocked
suppressed
```

Eligibility is a policy/human decision and cannot be granted by extraction or drafting models.

## 10. Route recommendation

The recommendation service may return:

```text
warm_introduction
existing_relationship
company_contact_form
public_role_inbox
public_individual_business_email
professional_profile_message
event_or_conference_connection
phone
research_more
do_not_contact
```

It can recommend a warm/event/existing route only when that human-origin route is already persisted. Recommendation is not permission.

## 11. Suppression

Synchronously check company, person, domain, and normalized route hash:

1. before target selection;
2. before packet creation;
3. before draft approval;
4. immediately before external provider action.

Explicit unsubscribe/objection creates suppression deterministically before any AI reply classification. Model output cannot remove or override suppression.

## 12. Freshness and invalidation

Configure route-specific stale windows. Role/person/route changes create new observations/versions rather than overwriting history. A stale or superseded selected route invalidates dependent packets and approvals.

## 13. Dashboard

Company `Contacts` tab separates:

```text
Buyer role hypotheses
People and role history
Public routes
Human-origin routes
Suppression
Selection history
```

Show provenance, retrieval/entry date, origin, observation, freshness, deliverability, eligibility, confidence, solution match, and row version. Never show a single generic “verified” badge.

## 14. Tests

- role-only result with no person;
- buyer role derives from solution requirements, not raw title alone;
- official contact form extraction;
- first-party `mailto` extraction;
- guessed email rejected;
- public extractor cannot emit warm introduction/event/existing relationship;
- human route requires user and provenance note;
- stale role history preserved;
- recruiter/employer ambiguity;
- duplicate normalized route HMAC;
- publication does not set deliverability;
- suppression blocks packet and action;
- hostile source instructions ignored;
- source/evidence references validated.

## 15. Acceptance criteria

- Every public person, role observation, and route is provenance-backed.
- Human-origin routes are explicit and auditable.
- No inferred email becomes a route.
- Observation, freshness, deliverability, eligibility, and recommendation remain separate.
- Buyer roles remain distinct from people.
- Suppression cannot be bypassed.
- Human target/route selection is required before packet creation.
