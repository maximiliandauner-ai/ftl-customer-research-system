# 11 — Signal Detection Agent

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Signal intelligence  
**Canonical prompt:** `signal_detector` version `2.0.0` in `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`

## 1. Purpose

Create observable, time-stamped, evidence-backed signal events from persisted posting lifecycle events. The agent answers only:

> Did the organization publicly perform a potentially relevant action, and which deterministic evidence items support that observation?

It does not evaluate commercial attractiveness, infer a buyer, design an FTL offer, or research the company.

## 2. Upstream inputs

Required:

```text
JobPosting
current JobPostingSnapshot
Posting lifecycle/material-change event
EvidenceCatalog and EvidenceItem rows
signal ontology version
prompt/model policy
PipelineRun
```

A search snippet, unpersisted webpage, or model-generated quote is not a valid input.

## 3. Input contract

```json
{
  "schema_version": "2.0",
  "event_context": {
    "event_kind": "created|material_change|reopened|closed|reposted",
    "occurred_at": null,
    "observed_at": "2026-08-05T08:00:00Z",
    "posting_id": "uuid",
    "snapshot_id": "uuid",
    "previous_snapshot_id": null
  },
  "posting_metadata": {
    "company_id": "uuid",
    "title": "...",
    "department": null,
    "employment_type": null,
    "seniority": null,
    "locations": []
  },
  "deterministic_change": {
    "change_type": "new",
    "added_evidence_ids": ["EV-000001"],
    "removed_evidence_ids": []
  },
  "evidence_catalog": [],
  "signal_ontology": {
    "version": "2.0",
    "allowed_signal_types": [
      "capability_hiring",
      "material_description_change",
      "role_reposted",
      "role_reopened",
      "role_closed"
    ],
    "allowed_capability_tags": []
  }
}
```

## 4. Output contract

Use `SignalDetectionResultV2` from `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`.

```json
{
  "schema_version": "2.0",
  "prompt_version": "2.0.0",
  "signals": [
    {
      "signal_type": "capability_hiring",
      "event_kind": "created",
      "capability_tags": ["learning_content", "creative_ai_production"],
      "supporting_evidence_ids": ["EV-000001", "EV-000002"],
      "confidence": 0.94,
      "concise_rationale": "The role explicitly includes AI-generated learning video and prompt-development responsibilities.",
      "review_flags": []
    }
  ],
  "no_signal_reason": null,
  "unknowns": []
}
```

## 5. Deterministic preprocessing

Before the model call:

1. load the canonical snapshot and catalog;
2. select relevant evidence candidates through deterministic keyword/section rules without discarding the complete context required by policy;
3. cap total source text by policy;
4. serialize evidence as IDs plus exact persisted text;
5. add untrusted-data boundaries;
6. compute input hash;
7. check existing idempotency key;
8. create `ProviderCall`/pipeline attempt.

The input may include exact text for the model to classify, but the output may reference only IDs.

## 6. Validation and persistence

For every returned signal:

- signal type and tags exist in active ontology;
- evidence IDs exist in the supplied catalog;
- evidence belongs to the current or explicitly allowed prior snapshot;
- capability-hiring/material-change signals have at least one supporting evidence item;
- event kind is compatible with deterministic lifecycle state;
- confidence is in range;
- no commercial claims appear in the rationale;
- no duplicate idempotency key exists.

Persist transactionally:

```text
SignalEvent
SignalEvidence junction rows
AuditEvent
TaskOutbox for capability classification, if eligible
```

The model's rationale is stored as a concise explanation. Evidence text is loaded from `EvidenceItem`, not copied from the response.

## 7. No-signal behavior

A valid no-signal result is useful. Store an assessment/attempt with:

```text
no relevant observable capability event
insufficient source evidence
only generic AI wording
unsupported event kind
source ambiguity
```

Do not create a weak signal merely to keep the pipeline moving.

## 8. Failure codes

```text
SOURCE_SNAPSHOT_MISSING
EVIDENCE_CATALOG_MISSING
EVIDENCE_REFERENCE_INVALID
ONTOLOGY_KEY_INVALID
SCHEMA_VALIDATION_FAILED
MODEL_REFUSAL
MODEL_INCOMPLETE
PROVIDER_TRANSIENT_FAILURE
DUPLICATE_SIGNAL
POLICY_BLOCKED
```

Schema/catalog failure allows at most one bounded retry. Permanent failure remains inspectable and does not create a signal.

## 9. UI

The signal detail shows:

- company and posting;
- source/lifecycle event;
- exact evidence loaded from the snapshot;
- prompt/model/schema/ontology versions;
- confidence and concise rationale;
- review flags;
- downstream classification status;
- ability to mark false positive/retract with reason.

## 10. Tests

- relevant German and English postings;
- generic AI mention with no actionable responsibility;
- hostile instructions embedded in job text;
- fabricated evidence ID returned by fixture model;
- material-change evidence from wrong snapshot;
- duplicate task execution;
- no-signal output;
- refusal/incomplete/schema failure;
- ontology-version change;
- retraction audit.

## 11. Acceptance criteria

- every active signal has persisted deterministic evidence;
- the model cannot create evidence text or IDs;
- signal creation is idempotent;
- no opportunity/service recommendation exists in this stage;
- false-positive review data is retained for evaluation;
- downstream classification begins only through a committed outbox row.
