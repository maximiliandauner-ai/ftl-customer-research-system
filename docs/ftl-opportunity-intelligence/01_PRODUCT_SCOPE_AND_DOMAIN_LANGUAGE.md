# 01 — Product Scope and Domain Language

**Document status:** Normative implementation specification  
**Specification version:** 2.1  
**Primary owner:** Product architecture  
**Audience:** Codex and FTL engineers

## 1. Purpose

Define the product boundary and the vocabulary every database model, Pydantic schema, prompt, service, interface, report, and analytics event must use consistently.

## 2. Product boundary

The platform MUST:

- discover public evidence of organizational demand;
- preserve sources, retrieval metadata, and immutable observations;
- create observed signal events without turning inference into fact;
- infer bounded capability gaps with evidence and uncertainty;
- aggregate company-level patterns and deterministic scores;
- research selected organizations with traceable sources;
- design a Create–Build–Deploy–Enable solution hypothesis;
- identify relevant buyer-role categories and legitimate public contact routes;
- prepare evidence-bound, unsent outreach for human approval;
- track decisions, suppression, interactions, outcomes, costs, and evaluation data.

The platform MUST NOT initially:

- bypass access controls or source restrictions;
- scrape authenticated or prohibited networks;
- treat every AI-related role as an FTL opportunity;
- guess personal email addresses;
- mark an inferred person, route, or need as verified;
- allow a model to approve or send first-contact outreach;
- become a generic applicant tracker, scraper, or mass-email system.

## 3. FTL value model

```python
from enum import StrEnum

class FTLLayer(StrEnum):
    CREATE = "create"
    BUILD = "build"
    DEPLOY = "deploy"
    ENABLE = "enable"
```

- **Create:** deliver the first visible content, experience, prototype, interface, or campaign result.
- **Build:** implement the reusable workflow, platform, automation, evaluation, or production system behind it.
- **Deploy:** establish cloud, private-cloud, hybrid, or local infrastructure and operational controls.
- **Enable:** document, train, govern, transfer, and help the internal team expand the capability.

## 4. Canonical domain terms

### 4.1 Source and observation terms

- **Source endpoint:** a monitored first-party feed, career page, sitemap, or other permitted public endpoint.
- **Source candidate:** a discovered URL or provider item that has not yet become evidence.
- **Fetch attempt:** one bounded network retrieval attempt, including failure and redirect metadata.
- **Source snapshot:** an immutable raw or parsed observation of a source at one retrieval time.
- **Job posting:** the durable identity of one posting across observations.
- **Job posting snapshot:** the immutable normalized state of that posting at one time.
- **Evidence catalog:** deterministic, versioned excerpts extracted from a persisted snapshot.
- **Evidence item:** exact source text with stable public ID, field path, hash, and optional offsets.

Search snippets and model-written quotations are not evidence.

### 4.2 Intelligence terms

- **Signal event:** an observed, source-backed lifecycle event, such as a relevant posting being created, materially changed, reopened, or closed.
- **Signal assessment:** a versioned interpretation of one signal against FTL ontologies and commercial criteria.
- **Capability gap:** a bounded inference that the organization may lack content, capacity, creative direction, workflow, platform, infrastructure, skills, governance, quality control, scaling, ownership, or experimentation capability.
- **Company pattern:** an inferred pattern over several observed signals, such as cross-department capability building. It is never stored as a `SignalEvent`.
- **Company assessment:** deterministic features, score components, selected signals, pattern records, cutoff time, and policy version for one company.
- **Opportunity:** an FTL-owned commercial hypothesis connected to one company and one or more signals. It is never synonymous with a job posting.

### 4.3 Research and solution terms

- **Research brief:** a bounded set of questions, source priorities, unknowns, disconfirming questions, and limits.
- **Research source:** a locally registered provider-returned source with canonical URL and retrieval provenance.
- **Research claim:** an observed fact, inference, hypothesis, or unknown tied to registered source IDs.
- **Solution hypothesis:** an editable phased Create–Build–Deploy–Enable recommendation. It is not a confirmed client requirement.
- **FTL knowledge release:** a versioned set of approved external claims, offers, modules, and assets that may be used downstream.

### 4.4 Contact and communication terms

- **Buyer-role hypothesis:** a role category that may own, operate, influence, or procure the proposed engagement.
- **Contact observation:** a public-source-backed or authorized human-confirmed observation about a professional person-role-company relationship.
- **Contact person:** a durable person record assembled only from relevant public observations.
- **Contact route:** a provenance-backed communication path. Public routes include contact forms, role inboxes, published business email, public professional profiles, and phone numbers. Human-origin routes include a documented warm introduction, existing relationship, or event connection.
- **Route origin:** whether a route comes from a public source, authorized human entry, an existing relationship, or an event.
- **Route observation status:** whether the exact route was explicitly observed or human-confirmed and with what provenance.
- **Deliverability status:** unknown, delivered, replied, bounced, or invalid; separate from source observation.
- **Outreach eligibility:** policy/human decision about whether the route may be used; separate from existence and deliverability.
- **Suppression entry:** a durable block for a company, person, domain, or route that model output cannot override.
- **Opportunity packet:** deterministic, immutable JSON assembled from approved current inputs for one downstream draft.
- **Outreach draft:** generated but unsent structured subject/body/short-message units tied to one packet, contact route, prompt/schema/model version, exact bindings, and deterministic rendered hashes.
- **Interaction:** an outgoing or incoming message, meeting, call, note, reply classification, or follow-up event.

## 5. Required engagement-mode keys

```text
done_for_you
pilot
pilot_plus_system
workflow_audit
internal_capability_build
local_ai_assessment
private_ai_deployment
managed_capability
capability_transfer
fractional_leadership
```

## 6. Required capability-gap keys

```text
content
production_capacity
creative_direction
workflow
platform
infrastructure
local_ai
data_governance
internal_skills
adoption
quality_control
scaling
ownership
experimentation
```

## 7. Claim-kind contract

Use these exact machine keys:

```text
observed_fact
inference
hypothesis
unknown
```

Example:

```json
{
  "claim_id": "CLM-000001",
  "statement": "The posting requests reusable prompt templates.",
  "claim_type": "observed_fact",
  "confidence": 0.98,
  "evidence_ids": ["EV-000004"],
  "source_ids": ["SRC-000001"]
}
```

Rules:

- `observed_fact` requires direct source support;
- `inference` requires support and cautious language;
- `hypothesis` is a testable commercial or organizational possibility;
- `unknown` records material missing information rather than filling it with a guess;
- a downstream stage may not silently upgrade an inference or hypothesis to an observed fact.

## 8. Opportunity mode

Use one mutually exclusive value:

```text
employment_only
external_service
hybrid
watch_signal
irrelevant
unknown
```

Store the selected mode, confidence, evidence IDs, and concise rationale. Do not represent `employment_only`, `external_service`, and `hybrid` as simultaneously independent probabilities.

## 9. Machine-key rules

- persisted keys are lower-case snake case;
- user-facing labels may be translated without changing persisted keys;
- enums live in one shared domain module;
- public evidence/source IDs are stable within their catalog/run;
- UUIDs identify database records; public IDs identify model-visible catalog entries;
- confidence is a float in `[0.0, 1.0]`;
- scores are integers in `[0, 100]`;
- timestamps are timezone-aware and persisted in UTC;
- uncertain values use explicit null/unknown semantics, never empty strings as hidden unknowns.

## 10. Downstream implementation contract

| Contract field | Required value |
|---|---|
| Upstream input | FTL product reference, founder-approved positioning, and audited architecture decisions |
| Primary output | Canonical vocabulary, enums, invariants, and product boundaries |
| Code targets | `domain/enums.py`, `domain/value_objects.py`, `domain/policies.py`, app ownership READMEs |
| Consumers | Django models, Pydantic schemas, Celery tasks, prompts, dashboard labels, analytics, tests |

## 11. Acceptance criteria

- shared enums are used by database, schemas, prompts, UI, and analytics;
- tests reject unknown or deprecated machine keys;
- source, observation, signal, pattern, opportunity, contact, and route are never used interchangeably;
- company patterns cannot be persisted as observed signal events;
- opportunity mode is mutually exclusive;
- claim kinds remain stable through downstream stages;
- contact observation, deliverability, freshness, and outreach eligibility remain separate;
- no production path contains placeholder ontology mappings.
