# 13 — Company Aggregation and Deterministic Scoring

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Opportunity intelligence

## 1. Purpose

Aggregate multiple posting/signals into one time-bounded company assessment, calculate deterministic features and scores, detect capability-building patterns, and create/update opportunity candidates without duplicating companies.

## 2. Inputs

```text
Company and verified CompanyDomain records
active/recent JobPosting records
SignalEvent records and evidence links
SignalAssessment component judgments
human qualification labels
scoring policy and ontology versions
feature cutoff timestamp
```

Company identity ambiguity blocks automatic aggregation and creates merge review.

## 3. Deterministic features

At minimum:

```text
related_roles_open
related_roles_added_30d
related_roles_added_90d
related_roles_closed_90d
roles_reopened_180d
roles_reposted_180d
distinct_departments_90d
distinct_capability_clusters_90d
seniority_distribution
employment_type_distribution
highest_signal_relevance
mean_signal_relevance
evidence_coverage_mean
creative_signal_count
learning_signal_count
automation_signal_count
infrastructure_signal_count
enablement_signal_count
first_party_source_ratio
signal_recency_days
source_health
```

Every feature record stores:

```text
feature_key
value
unit
cutoff_at
input record IDs/hash
feature_builder_version
```

## 4. Company pattern rules

Rules identify candidate patterns before optional narrative generation.

```text
isolated_experiment
cross_functional_capability_build
production_capacity_expansion
internal_platform_build
learning_and_enablement_program
local_private_ai_investment
mature_internal_team
weak_or_ambiguous_pattern
```

Example deterministic rule:

```text
cross_functional_capability_build when:
- >= 2 relevant roles in 90 days;
- >= 2 distinct departments;
- >= 2 capability clusters;
- mean evidence coverage >= threshold.
```

Rules are versioned and tested. A model MAY produce a human-readable narrative using `company_pattern_synthesizer`; it does not alter the deterministic pattern or score.

## 5. Score components

### 5.1 Capability relevance

Derived from signal assessments weighted by evidence coverage, source priority, recency, and relation to current open roles.

### 5.2 Commercial actionability

Components:

```text
problem clarity
organizational commitment
vendor/partner receptivity
owner clarity
contactability
hybrid-delivery plausibility
corroboration
```

Some remain unknown before research. Store coverage.

### 5.3 Long-term system potential

```text
recurring use-case potential
cross-department reach
workflow volume/scaling need
reproducibility/governance need
infrastructure/privacy need
capability-transfer potential
continued partnership potential
```

### 5.4 Strategic value

Based on configured FTL policy and optional human input:

```text
brand/reputation fit
case-study potential
international relevance
creative ambition
technical depth
market adjacency
portfolio differentiation
relationship potential
```

A model may suggest values after research, but FTL policy/manual inputs remain authoritative.

## 6. Priority calculation

Initial versioned formula:

```text
priority_score =
    0.40 * capability_relevance
  + 0.25 * commercial_actionability
  + 0.20 * long_term_system_potential
  + 0.15 * strategic_value
```

### Missing-data policy

The scoring service MUST return:

```json
{
  "score": 77,
  "coverage": 0.78,
  "missing_components": ["vendor_receptivity"],
  "policy_version": "2.0"
}
```

Choose and document one policy:

- normalize weights over known components while applying a coverage penalty; or
- impute configured neutral priors and expose uncertainty.

Do not silently treat unknown as zero. The initial recommended policy is normalized known weights plus a modest configurable coverage penalty, validated on the review dataset.

## 7. CompanyAssessment output

```json
{
  "schema_version": "2.0",
  "company_id": "uuid",
  "feature_cutoff_at": "2026-08-05T08:00:00Z",
  "feature_builder_version": "2.0",
  "scoring_policy_version": "2.0",
  "features": {},
  "pattern_keys": ["cross_functional_capability_build"],
  "capability_relevance": {"score": 88, "coverage": 0.94},
  "commercial_actionability": {"score": 61, "coverage": 0.54},
  "long_term_system_potential": {"score": 83, "coverage": 0.77},
  "strategic_value": {"score": 70, "coverage": 0.60},
  "priority_score": 78,
  "overall_coverage": 0.75,
  "selected_signal_ids": ["uuid"],
  "unknowns": [],
  "review_flags": []
}
```

## 8. Opportunity creation/update

Create one active opportunity candidate per company and primary use-case family unless human policy permits multiple distinct opportunities.

Rules:

- do not create from discovery candidates alone;
- require at least one active evidence-backed signal;
- keep signal-to-opportunity many-to-many links;
- update existing opportunity when related signals arrive;
- create a new opportunity only when the use case/buyer area is materially distinct;
- preserve score history rather than overwriting prior assessment.

## 9. Time decay and currentness

- Recency is deterministic from source dates/observations.
- Closed signals may remain relevant with reduced weight.
- Stale research does not remain fully actionable.
- Reopened or materially changed roles can refresh momentum.
- Time-decay functions are versioned and tested.

## 10. Controls

- human overrides stored separately with actor/reason;
- automatic ranking cannot qualify or reject externally;
- low coverage may cap routing tier;
- source/company ambiguity blocks automatic opportunity creation;
- policy changes trigger re-score jobs, not destructive rewrites.

## 11. Dashboard

Company ranking page shows:

- overall priority and coverage;
- all four component scores;
- deterministic feature summary;
- pattern labels;
- signal timeline;
- missing information;
- previous assessments/score movement;
- scoring-policy version;
- human override/qualification.

## 12. Tests

- aggregation windows and cutoff reproducibility;
- cross-department pattern fixtures;
- unknown/missing-data policy;
- score formula exactness;
- time decay;
- closed/reopened roles;
- duplicate company ambiguity;
- one active opportunity per use-case family;
- policy-version re-score;
- human override separation.

## 13. Acceptance criteria

- identical inputs/cutoff/policy produce identical features and scores;
- every score is decomposable and queryable;
- unknown values are not treated as known negatives;
- company patterns are supported by selected signals;
- model narrative cannot change deterministic ranking;
- opportunity creation is idempotent and reviewable.
