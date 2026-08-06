# 23 — Dashboard UX and Interface Specification

**Specification version:** 2.1  
**Primary owner:** Product design and frontend

## Purpose

Define the complete operational information architecture, page hierarchy, components, state visibility, source linking, and premium FTL visual direction for a Django/HTMX interface.

## Design objective

The interface should feel like a precise creative-technology control room: dark, cinematic, restrained, premium, and highly legible. Evidence, decisions, and next action take precedence over decorative effects.

## Technical UI architecture

- Django templates and forms.
- HTMX for filtering, drawers, inline state changes, task initiation, polling, and partial refresh.
- Tailwind CSS or a small tokenized CSS layer.
- Progressive enhancement: critical review and approval actions work without custom JavaScript.
- Server-side filtering, sorting, pagination, and permissions.
- URL-persisted filters and saved views.
- No separate SPA in the first implementation.

## Global shell

```text
Left navigation: 240–264 px
Top bar: global search, active runs, alerts, current user
Main region: dense responsive operational content
Optional right drawer: source, task, edit, or history context
```

Navigation:

```text
Overview
Signal Inbox
Companies
Opportunities
Research
Contacts
Outreach
Knowledge Library
Analytics
Operations
Settings
```

## Visual tokens

- Near-black page background and slightly elevated neutral surfaces.
- High-contrast neutral typography; Geist/Inter/system stack.
- One restrained accent for active selection, not for every card.
- 1px borders and subtle elevation.
- Status uses text + icon + shape, never color alone.
- Limited motion; honor `prefers-reduced-motion`.
- Minimum 44 px interactive targets where practical.
- Do not use glass blur behind dense tables.
- Dates display in Europe/Berlin with UTC tooltip where operationally useful.

## 1. Overview `/`

### Top metrics

- new signals since last review;
- high-priority unreviewed companies;
- research running/failed;
- solutions awaiting review;
- drafts awaiting approval;
- follow-ups due;
- failed pipeline/outbox items;
- daily/monthly OpenAI cost.

### Main content

- priority opportunity queue;
- recent signal timeline;
- active/failed research;
- review backlog;
- worker/Beat/outbox health;
- recent human decisions.

Every metric links to a filtered operational page.

## 2. Signal Inbox `/signals/`

### Table columns

```text
selection
priority
company
role and source type
location
observed/published date
exact capability evidence indicator
capability gaps
recommended FTL layers
company pattern indicator
research state
qualification
owner
next action
row actions
```

### Row expansion

The expansion shows:

- exact evidence quotes with source section;
- first-party/source status;
- source URL and retrieval time;
- classifier facts, inferences, unknowns, and flags;
- score components and scoring policy version;
- related/duplicate postings;
- pipeline and provider-call links.

### Actions

```text
Qualify
Watch
Mark employment-only
Reject with reason
Open company
Start standard research
Assign owner
Open original source
```

Bulk actions exclude external communication and suppression removal.

## 3. Company list `/companies/`

Filters:

- company priority;
- capability clusters/gaps;
- active patterns;
- location/country/industry;
- hiring momentum;
- research freshness;
- qualification/relationship state;
- owner;
- suppression.

Cards are not used for the primary list; use a compact table with optional saved board view.

## 4. Company detail `/companies/<id>/`

### Header

```text
Company name
verified primary domain
industry and locations
watch/suppression state
owner
company priority
hiring momentum
last researched
next action
```

### Tabs

1. **Overview**
2. **Signals & Jobs**
3. **Research**
4. **Opportunities**
5. **Contacts**
6. **Outreach**
7. **Interactions**
8. **Audit**

### Overview tab

- company assessment and policy version;
- capability-gap heatmap;
- Create–Build–Deploy–Enable relevance;
- active `CompanyPattern` cards clearly labeled **Inference**;
- source freshness;
- relevant departments;
- current opportunities and next actions.

### Signals & Jobs tab

- chronological job/source records;
- current/closed status;
- snapshot diff viewer;
- exact signal evidence;
- duplicate/translation relationships;
- source and artifact links.

### Research tab

- current report summary;
- claim list with fact/inference labels;
- inline source chips opening the source drawer;
- complete source registry, including consulted-but-not-cited sources;
- unknowns and discovery questions;
- standard/deep run history and costs.

### Contacts tab

- buyer-role hypotheses grouped by economic, functional, technical/security, and champion roles;
- observed public professionals and official routes;
- route origin/provenance, source or human provenance, retrieval/entry date, observation, freshness, deliverability, eligibility, legal-route review, and suppression;
- human target-selection control;
- associated drafts/interactions.

### Outreach tab

This is where all company-specific drafts are found. Show:

- draft status/version;
- subject and channel;
- selected target route;
- packet hash/version;
- factual-review state;
- approver/time;
- external draft/message reference;
- deterministic structured-unit preview with per-unit source/claim bindings;
- version history and diffs.

## 5. Opportunity detail `/opportunities/<id>/`

### Main column

- observed signal evidence;
- company patterns labeled inference;
- research claims/source links;
- capability gaps;
- problem hypothesis;
- phased solution editor;
- current target and draft history;
- interactions and outcomes.

### Sticky side rail

```text
priority and score dimensions
owner
qualification/research/solution/contact/outreach/relationship states
next action/date
selected entry offer
selected target route
selected assets
safe action buttons
```

## 6. Research workspace `/research/<run_id>/`

Display:

- research brief and input hash;
- model/prompt/tool policy;
- live state and next poll;
- tool-call/source count and cost;
- raw cited report rendered safely;
- structured claims and source bindings;
- source registry and annotations;
- unknowns/warnings;
- failure code and safe retry/supersede actions.

Never render raw arbitrary HTML from sources.

## 7. Solution designer `/opportunities/<id>/solution/`

Sections:

1. problem hypothesis and evidence;
2. entry offer;
3. FTL layers;
4. phase editor with order, objective, deliverables, inputs, success criteria, assumptions;
5. infrastructure mode/rationale/discovery questions;
6. long-term operating model;
7. internal-hire complementarity;
8. buyer-role requirements;
9. asset-match requirements;
10. risks, unknowns, and `do_not_claim`;
11. version diff and approval.

HTMX reordering must remain keyboard-accessible or provide explicit move buttons.

## 8. Asset matching `/opportunities/<id>/assets/`

- current approved solution and match requirements;
- filtered active public FTL asset candidates;
- selected zero-to-two assets with phase relevance;
- rejected/confidential/stale asset reasons;
- immutable asset-match version and approval/currentness state.

## 9. Contact selection `/opportunities/<id>/contacts/`

- role hypotheses with decision-role fit;
- public and explicit human-origin route lists;
- named observations only when sourced;
- route origin, provenance, observation, freshness, deliverability, and eligibility;
- suppression/legal review badges;
- select target button requiring human confirmation;
- link to source page and company Contacts tab.

## 10. Outreach review `/outreach/drafts/<id>/`

Three-column desktop layout, stacked on smaller screens:

### Left: evidence context

- selected signal quotes;
- research claims and sources;
- solution and `do_not_claim`;
- approved FTL claims/assets.

### Center: message

- subject options;
- editable plaintext body;
- channel preview;
- statement-by-statement binding markers;
- version diff;
- regeneration instruction field.

### Right: controls

- target route/source/freshness;
- deterministic findings;
- optional AI critic findings;
- suppression/legal state;
- packet/prompt/model versions;
- approve, revise, change target, reject, do-not-contact.

Clicking a statement highlights its evidence/source. Clicking a source opens a safe external link in a new tab and the local source metadata drawer.

## 11. Knowledge Library `/knowledge/`

- active and historical releases;
- offer modules;
- approved/prohibited claims;
- public/internal/confidential assets;
- URL/review freshness;
- sync validation report;
- activation controls restricted to founders/admins.

## 12. Operations `/operations/`

Pages:

```text
Pipeline runs
Task outbox
Celery queues/workers
Schedules/Beat
Provider calls and cost
Webhooks
Source health
Artifacts/retention
Backups/restores
Configuration health
```

Failures show safe context, attempts, next retry, and retry/abandon controls. Secrets and raw sensitive payloads are never shown by default.

## 13. Accessibility and safety

- Semantic headings, tables, forms, labels, and live regions.
- Visible focus and keyboard operation.
- Color contrast and reduced motion.
- Confirmation for destructive/external actions.
- CSRF on every state-changing HTMX request.
- Permission errors render explicit 403 pages, not hidden controls alone.
- Pagination and filters remain navigable by URL.

## 14. Acceptance criteria

- A signal can be qualified from the inbox/detail view.
- Every company exposes its sources, contacts, drafts, and interactions in predictable tabs.
- A reviewer can trace each draft statement to evidence/approved FTL claims.
- Failures/outbox backlog are visible without container logs.
- Critical flows work with keyboard and progressive enhancement.
- E2E tests cover qualification, research view, solution approval, target selection, draft review, approval invalidation, and suppression.
