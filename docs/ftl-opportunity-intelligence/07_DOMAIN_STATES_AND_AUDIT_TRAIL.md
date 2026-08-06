# 07 — Domain States, Transitions, Ownership, and Audit Trail

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Domain architecture  
**Audience:** Codex and FTL engineers

## 1. Purpose

Define independent state machines, legal transitions, actor permissions, optimistic concurrency, and append-only audit requirements.

## 2. Why states are independent

Research, qualification, solution design, outreach, and commercial relationship progress are different concerns. They MUST NOT compete for one generic `status` field.

## 3. State families

### 3.1 Source lifecycle

```text
candidate
registered
active
degraded
blocked
archived
```

### 3.2 Posting lifecycle

```text
unknown
open
closed
expired
```

### 3.3 Pipeline/research state

```text
new
queued
running
partial
complete
failed
canceled
expired
review_required
```

### 3.4 Qualification

```text
unreviewed
watchlist
qualified
employment_only
hybrid_opportunity
service_opportunity
rejected
duplicate
expired
```

### 3.5 Solution

```text
not_started
draft
under_review
approved
rejected
superseded
```

### 3.6 Outreach

```text
not_started
packet_blocked
strategy_ready
draft_ready
needs_revision
ready_for_human
human_approved
external_draft_created
sent
follow_up_due
replied
closed
do_not_contact
```

The initial product MUST NOT transition directly from generated draft to `sent`.

### 3.7 Relationship stage

```text
prospect
conversation
discovery
pilot_discussion
proposal
won
lost
future_opportunity
```

### 3.8 Contact-route state families

Route origin/provenance, observation, freshness, deliverability, policy eligibility, recommendation, and suppression are independent.

```text
route_origin:
  public_source | human_entered | existing_relationship | event

observation_status:
  published_officially | published_third_party | human_confirmed | unconfirmed | disputed

freshness_status:
  current | stale | unknown

deliverability_status:
  unknown | delivered | replied | bounced | invalid

outreach_eligibility:
  unreviewed | eligible_after_human_review | blocked | suppressed

record_status:
  active | stale | invalid | suppressed
```

Do not present one generic `verified` status in code or the UI.

## 4. Transition services

Every state change uses a domain service such as:

```python
class QualificationService:
    def qualify(self, opportunity_id: UUID, actor: User, reason: str) -> Opportunity: ...
    def reject(self, opportunity_id: UUID, actor: User, reason_key: str, note: str | None) -> Opportunity: ...

class OutreachApprovalService:
    def approve(self, draft_id: UUID, expected_version: int, actor: User, comment: str | None) -> ApprovalDecision: ...
```

Direct `.status = ...; save()` from views/tasks is prohibited for audited transitions.

Each transition:

1. reloads the row with appropriate lock/version check;
2. validates current state and preconditions;
3. updates state and `row_version`;
4. writes `AuditEvent` in the same transaction;
5. creates `TaskOutbox` if asynchronous continuation is needed;
6. returns the new state.

## 5. Transition matrix examples

### 5.1 Qualification

| From | To | Actor | Preconditions |
|---|---|---|---|
| unreviewed | watchlist | reviewer | reason optional |
| unreviewed/watchlist | qualified | reviewer | at least one active signal |
| unreviewed/watchlist | employment_only | reviewer | reason required |
| qualified | rejected | reviewer/admin | reason required |
| rejected | watchlist | reviewer/admin | explicit reopen reason |

### 5.2 Solution

| From | To | Actor |
|---|---|---|
| not_started | draft | system/agent |
| draft | under_review | system/user |
| under_review | approved | human reviewer |
| approved | superseded | system when inputs materially change |
| any non-final | rejected | human reviewer |

### 5.3 Draft/approval

| From | To | Actor | Preconditions |
|---|---|---|---|
| strategy_ready | draft_ready | drafting task | valid packet |
| draft_ready | ready_for_human | evidence review | no blocking issue |
| ready_for_human | human_approved | human | exact draft hash |
| human_approved | needs_revision | system/user | content unit/subject/asset/renderer/packet/route changed |
| human_approved | external_draft_created | human/provider adapter | provider integration enabled |
| external_draft_created | sent | human/sync | verified provider message record |

## 6. Automatic versus human transitions

### Automatic allowed

- source health changes based on deterministic thresholds;
- posting open/closed/reopened from validated observations;
- task/research state;
- draft generation;
- stale/superseded state when upstream versions change;
- reply classifier suggestion;
- immediate suppression on explicit unsubscribe/objection.

### Human required

- opportunity qualification or commercial rejection;
- solution approval;
- contact-route selection for first outreach;
- external message approval;
- send or external-draft creation in the initial product;
- merge decision for ambiguous companies/contacts;
- suppression removal;
- legal/compliance exception.

## 7. AuditEvent

```json
{
  "event_id": "uuid",
  "occurred_at": "2026-08-05T09:00:00Z",
  "actor_type": "user|system|provider",
  "actor_id": "uuid|null",
  "action": "opportunity.qualified",
  "object_type": "opportunity",
  "object_id": "uuid",
  "before": {"qualification_status": "unreviewed", "row_version": 4},
  "after": {"qualification_status": "qualified", "row_version": 5},
  "reason_key": "strong_signal_fit",
  "note": null,
  "request_id": "uuid|null",
  "trace_id": "uuid|null",
  "pipeline_run_id": "uuid|null"
}
```

Audit records are append-only. Sensitive body content should be referenced by object/version/hash rather than copied into every event.

## 8. Concurrency

- Use optimistic concurrency (`row_version`) for interactive editors.
- Return HTTP 409 with current version when stale edits occur.
- Use `select_for_update()` for short critical transitions.
- Never hold database locks during external provider calls.
- Bulk actions process each item transactionally and report partial failure.

## 9. Ownership

Opportunities may be unassigned or owned by an active team member. Reassignment is audited. Deactivating a user does not delete historical authorship; open items must be explicitly reassigned or shown as unassigned.

## 10. Rejection and review reasons

Use configured keys rather than only free text:

```text
wrong_industry
employment_only
weak_evidence
insufficient_system_potential
no_credible_ftl_offer
outdated
company_too_small
company_too_large_or_mature
duplicate
contact_risk
compliance_risk
not_strategically_relevant
other
```

A note is required for `other`.

## 11. Tests

- every legal transition;
- every illegal transition;
- permission failures;
- stale row-version conflict;
- transition + audit atomicity;
- transition + outbox atomicity;
- approval invalidation after edit;
- suppression priority;
- bulk partial results;
- historical author retained after user deactivation.

## 12. Acceptance criteria

- no audited state can be changed outside its service in production code;
- all transitions appear in company/opportunity timeline;
- concurrent edits cannot silently overwrite each other;
- automated generation never equals human approval;
- suppression blocks packet/draft/external actions synchronously.
