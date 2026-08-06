# 12 — Capability-Gap Classification Agent

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Opportunity intelligence  
**Canonical prompt:** `capability_gap_classifier` version `2.1.0`

## 1. Purpose

Interpret an approved signal against FTL’s versioned ontology. Identify capability overlap, plausible organizational gaps, one mutually exclusive opportunity mode, FTL layers, and score components. The stage does not perform web research and does not calculate the final weighted score in the model.

## 2. Questions answered

- Which FTL capability clusters are explicitly supported?
- Which capability gaps are plausibly revealed?
- Which single configured opportunity mode best describes the current evidence: employment-only, external service, hybrid, watch signal, irrelevant, or unknown?
- Which Create–Build–Deploy–Enable layers merit later investigation?
- Which entry offers are plausible?
- What remains unknown?

## 3. Opportunity-mode contract

Use exactly one configured mode:

```text
employment_only
external_service
hybrid
watch_signal
irrelevant
unknown
```

Store the selected mode, confidence, supporting evidence IDs, and a concise rationale. This avoids false numerical precision while keeping the categories mutually exclusive.

Vendor receptivity, infrastructure relevance, and long-term system potential are separate judgments and may remain unknown.

## 4. Input

```json
{
  "schema_version": "2.1",
  "signal": {
    "signal_id": "uuid",
    "signal_type": "capability_hiring",
    "event_kind": "created",
    "capability_tags": []
  },
  "posting_context": {
    "title": "...",
    "department": null,
    "employment_type": "working_student",
    "seniority": null,
    "locations": []
  },
  "evidence_catalog": [],
  "ftl_ontology": {
    "version": "2.0",
    "capability_clusters": [],
    "capability_gaps": [],
    "ftl_layers": ["create", "build", "deploy", "enable"],
    "entry_offer_keys": [],
    "opportunity_modes": [
      "employment_only",
      "external_service",
      "hybrid",
      "watch_signal",
      "irrelevant",
      "unknown"
    ]
  },
  "classification_policy_version": "2.1"
}
```

## 5. Output

Use `CapabilityAssessmentV2` from `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`.

Core fields:

```json
{
  "schema_version": "2.1",
  "prompt_version": "2.1.0",
  "capability_clusters": [],
  "capability_gaps": [],
  "opportunity_mode": "hybrid",
  "mode_confidence": 0.76,
  "mode_evidence_ids": ["EV-000001", "EV-000002"],
  "mode_rationale": "The posting supports internal hiring while its system-building scope makes an external contribution plausible.",
  "recommended_ftl_layers": ["create", "build", "enable"],
  "entry_offer_candidates": [],
  "component_judgments": {
    "task_overlap": {"score": 92, "confidence": 0.91},
    "reusable_system_potential": {"score": 78, "confidence": 0.72},
    "enablement_potential": {"score": 74, "confidence": 0.68},
    "infrastructure_relevance": {"value": "unknown", "confidence": 0.42},
    "vendor_receptivity": {"value": "unknown", "confidence": 0.36}
  },
  "unknowns": [],
  "review_flags": []
}
```

## 6. Scoring ownership

The model returns bounded components. Python calculates:

### Capability relevance

```text
task overlap                         25%
FTL capability overlap               20%
reusable-system potential            15%
infrastructure-work potential        10%
enablement potential                 10%
portfolio-proof availability         10%
industry/strategic relevance         10%
```

At this stage, dimensions requiring company research or manual FTL policy may be `unknown`. The scoring service applies a versioned missing-data policy and returns both score and coverage.

### Deterministic dimensions

- signal recency from timestamps;
- employment type/seniority features from normalized fields;
- number of supported evidence items;
- evidence coverage;
- ontology/offer/asset availability from database.

The model does not calculate recency or final priority.

## 7. Missing data

Unknown is distinct from zero.

Store:

```text
value nullable
confidence
coverage
unknown reason
```

A company should not be penalized as definitely unreceptive merely because vendor receptivity is unknown.

## 8. Routing

Initial configurable policy:

```text
priority < 40             archive/reject suggestion, human-configurable
40–54                     watchlist
55–74                     standard company research eligible
75–89                     high-priority review/research
90–100                    founder review
```

Routing also considers:

- minimum evidence coverage;
- `opportunity_mode` and `mode_confidence`;
- policy/compliance flags;
- duplicate/company ambiguity;
- budget availability.

The thresholds are not hardcoded in the prompt.

## 9. Persistence

Persist:

```text
SignalAssessment
CapabilityGapRecord rows
assessment-to-evidence links
resolved model/prompt/schema/ontology/policy snapshots
component values and confidence
Python-computed scores and coverage
input/output hashes
ProviderCall
AuditEvent
TaskOutbox for next eligible stage
```

## 10. Review UI

Show:

- exact evidence beside each cluster/gap;
- opportunity mode, confidence, rationale, and supporting evidence;
- component score, confidence, and missing-data state;
- Python formula/policy version;
- overall score and evidence coverage;
- unknowns and flags;
- human override with required reason.

Overrides do not rewrite model output; they create reviewed values and audit events.

## 11. Tests

- opportunity-mode enum and confidence validation;
- unknown versus zero;
- unsupported ontology/offer key;
- fabricated evidence ID;
- local-AI recommendation without evidence;
- deterministic score reproduction;
- scoring-policy version change;
- weak evidence blocks high-priority routing;
- German/English evaluation set;
- hostile source instructions;
- human override audit.

## 12. Acceptance criteria

- opportunity mode is mutually exclusive and no overlapping probability fields remain;
- all output references validated ontology/evidence IDs;
- Python reproduces scores from stored components/policy;
- missing evidence remains unknown;
- model output cannot route directly to outreach;
- every assessment is explainable in the dashboard.
