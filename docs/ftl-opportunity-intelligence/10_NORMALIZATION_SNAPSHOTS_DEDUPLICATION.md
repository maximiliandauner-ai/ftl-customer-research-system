# 10 — Normalization, Snapshots, Evidence, Deduplication, and Posting Lifecycle

**Document status:** Normative implementation specification  
**Revision:** 2.1  
**Primary owner:** Data ingestion  
**Audience:** Codex and FTL engineers

## 1. Purpose

Create canonical company/posting records, immutable normalized history, deterministic evidence catalogs, material-change events, non-destructive duplicate relationships, and reliable open/closed lifecycle state.

## 2. Input

```text
ParsedPostingDTO
SourceSnapshot
FetchAttempt/PostingObservation
existing Company/CompanyDomain/JobPosting records
normalizer and evidence-builder versions
```

## 3. Output

```json
{
  "schema_version": "2.0",
  "company_id": "uuid",
  "job_posting_id": "uuid",
  "job_posting_snapshot_id": "uuid",
  "evidence_catalog_id": "uuid",
  "change_type": "new|unchanged|cosmetic|material|closed|reopened",
  "changed_fields": ["description_text"],
  "previous_snapshot_id": "uuid|null",
  "signal_detection_required": true,
  "duplicate_relationship_id": null,
  "review_flags": []
}
```

## 4. Company resolution

Resolve in order:

1. existing provider-to-company mapping;
2. human-verified company domain;
3. source-confirmed hiring-organization domain;
4. exact reviewed alias;
5. create provisional company and merge-review candidate.

Do not:

- map a company from an ATS host alone;
- auto-merge companies solely by similar name;
- treat a recruitment agency as the employer without source evidence;
- assume one company has only one domain.

Ambiguity creates `CompanyMergeReview` and may block company-level aggregation until resolved.

## 5. URL canonicalization

Store original and canonical URLs.

Canonicalization:

- lowercase scheme/host;
- IDNA ASCII host;
- remove default port;
- normalize empty path;
- remove fragment;
- sort query parameters only when semantics are preserved;
- remove only configured tracking parameters (`utm_*`, known click IDs);
- preserve functional/signed ATS parameters;
- avoid provider-specific rewrites without tests.

## 6. Text normalization

Maintain two representations:

### Display/source text

Preserves paragraph/list structure and meaningful punctuation.

### Semantic comparison text

- Unicode NFC/NFKC according to documented policy;
- normalized whitespace;
- boilerplate removed by connector rule;
- stable heading/list markers;
- no aggressive stemming or translation;
- sensitive transformations versioned.

Hash both full and semantic content. A normalizer version change does not retroactively rewrite immutable snapshots; it creates a reprocessing path.

## 7. Snapshot process

Within one transaction:

1. resolve company/posting;
2. persist posting snapshot when hash is new;
3. create posting observation;
4. build deterministic evidence catalog;
5. compare with previous current snapshot;
6. create deterministic diff;
7. run material-change classifier only if rules cannot decide;
8. update current pointer/lifecycle;
9. create audit record;
10. create task-outbox continuation when signal detection is required.

## 8. Evidence catalog builder

The application, not the model, builds evidence.

### 8.1 Segmentation

Segment normalized fields into stable items:

```text
title
summary paragraphs
responsibility bullets
requirement bullets
offer/benefit bullets
employment/location metadata
```

Each item receives:

```json
{
  "evidence_id": "EV-000001",
  "snapshot_id": "uuid",
  "field_path": "description.responsibilities[2]",
  "exact_text": "Develop reusable prompts for scripts, voice and video.",
  "normalized_text": "Develop reusable prompts for scripts, voice and video.",
  "start_char": 1024,
  "end_char": 1082,
  "language": "en",
  "content_sha256": "..."
}
```

### 8.2 Validation

- exact text matches persisted field text;
- offsets, when stored, are verified after normalization;
- stable ordering makes IDs reproducible for identical snapshot/builder version;
- item length is bounded; oversized paragraphs are split deterministically;
- boilerplate is marked or excluded by policy;
- search snippets never enter the catalog.

Agents return evidence IDs only. The service materializes quotes from this catalog.

## 9. Deterministic diff

Compute:

```text
field additions/removals
metadata changes
ordered evidence-item additions/removals
text similarity
section-level changes
content hashes
```

Rules decide clear cases:

- identical semantic hash -> unchanged;
- formatting/boilerplate-only -> cosmetic;
- title, employment, location, or status metadata change -> configured deterministic class;
- newly opened record -> new;
- explicit reopen -> reopened;
- clear new/removed capability-relevant evidence -> material.

Ambiguous description changes use `material_change_classifier` prompt `2.0.0` from `33_AGENT_PROMPT_ENGINEERING_STANDARD.md`.

The model receives a deterministic diff and evidence catalog; it cannot create new evidence text.

## 10. Change classes

```text
new
unchanged
cosmetic
material
closed
reopened
```

A material change includes, when supported:

- AI/creative responsibility added;
- reusable system/workflow responsibility added;
- local/private infrastructure requirement added;
- enablement/workshop/governance responsibility added;
- seniority/ownership materially changed;
- employment/contract materially changed;
- substantial rewrite that changes capability interpretation.

## 11. Posting identity and deduplication

Use layered deterministic candidates:

1. same source endpoint + provider external ID;
2. same canonical URL/provider;
3. same verified company + normalized title + location + near publication window;
4. same semantic content hash;
5. semantic candidate requiring review.

Never auto-merge solely from embeddings or a model assertion.

`DuplicateRelationship` types:

```text
duplicate
translation
syndicated
related
```

First-party employer/ATS source is normally primary. Secondary records and snapshots remain queryable.

## 12. Semantic review

Semantic similarity MAY identify duplicate candidates after deterministic rules. It must:

- store method/model/version/input hashes;
- never auto-merge above a score without evaluated policy;
- include title/company/location mismatch flags;
- expose candidates to human review;
- preserve both records if rejected.

Start without embeddings unless evaluation proves they improve precision/recall enough to justify complexity.

## 13. Posting closure

Closure evidence, in priority order:

1. explicit provider closed state;
2. first-party 404/410 verified for the posting URL;
3. valid-through expiration plus source confirmation policy;
4. absence across `N` successful complete endpoint polls;
5. human decision.

Rules:

- source failure/timeout/blocked poll does not count as absence;
- partial pagination failure does not count as absence;
- one absent poll does not close by default;
- reopening creates a lifecycle event and may create a signal;
- closed postings remain historically visible.

## 14. Idempotency

- unique snapshot hash per posting;
- unique evidence catalog per snapshot/builder version;
- unique observation per posting/source poll;
- unique lifecycle event per posting/change basis;
- repeated task returns existing IDs;
- downstream signal key includes snapshot/event/prompt version.

## 15. Dashboard behavior

Posting page shows:

- current normalized fields;
- source and first/last seen;
- snapshot timeline;
- section-level diff;
- evidence IDs and exact source text;
- duplicate/translation relationships;
- lifecycle observations;
- parsing warnings;
- downstream signal/assessment state.

No raw unsanitized HTML is rendered.

## 16. Tests

- URL tracking versus functional parameter behavior;
- Unicode/whitespace normalization;
- evidence ID reproducibility;
- exact evidence validation;
- identical fetch idempotency;
- cosmetic versus material change fixtures;
- invalid model evidence ID rejection;
- provider ID and canonical URL dedup;
- translation relationship preservation;
- ambiguous company merge review;
- closure across successful polls only;
- reopen behavior;
- normalizer/evidence-builder version reprocessing.

## 17. Acceptance criteria

- Repeated identical source content creates no duplicate snapshot or signal.
- Every signal-supporting evidence item is deterministically traceable to a snapshot.
- Model-generated quotes are never accepted as evidence.
- Functional URLs are preserved.
- Ambiguous company/posting matches require review.
- Closure cannot result from source outage alone.
- Historical snapshots and duplicate relationships remain visible.
