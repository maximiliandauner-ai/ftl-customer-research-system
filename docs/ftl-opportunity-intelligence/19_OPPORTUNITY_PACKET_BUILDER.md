# 19 — Deterministic Opportunity Packet Builder

**Specification version:** 2.1  
**Primary owner:** Application services

## Purpose

Assemble a compact, immutable, deterministic JSON context for drafting and factual review after solution approval, current asset matching, buyer-role inference, and human target/route selection.

## Principle

The packet builder is Python, not an LLM. It selects approved/current records, prevents irrelevant/private context leakage, and creates a stable input manifest and hash.

## Upstream input

- current qualified opportunity and owner;
- selected observed signals/evidence;
- current company assessment/patterns;
- non-stale research claims and source registry;
- approved solution hypothesis;
- human-selected buyer role/contact route;
- current `AssetMatchResultV2` (including an explicit zero-asset result) plus active public FTL claims/assets;
- communication policy;
- relevant prior interactions;
- suppression/legal-route state.

## OpportunityPacketV2

```json
{
  "schema_version": "2.1",
  "packet_id": "uuid",
  "generated_at": "ISO-8601",
  "opportunity": {
    "id": "uuid",
    "name": "...",
    "priority": 82,
    "owner_id": "uuid"
  },
  "company": {
    "id": "uuid",
    "name": "...",
    "domain": "...",
    "industry": "...",
    "locations": []
  },
  "signals": [
    {
      "signal_id": "uuid",
      "type": "capability_hiring",
      "title": "...",
      "observed_at": "ISO-8601",
      "source_url": "https://...",
      "evidence": [
        {"evidence_id": "EV-000001", "exact_text": "...", "source_snapshot_id": "uuid"}
      ]
    }
  ],
  "research_claims": [
    {
      "claim_id": "CLM-000001",
      "statement": "...",
      "claim_type": "observed_fact|inference|hypothesis|unknown",
      "source_ids": ["SRC-000001"],
      "confidence": 0.91
    }
  ],
  "sources": [
    {"source_id": "SRC-000001", "url": "https://...", "title": "...", "retrieved_at": "ISO-8601"}
  ],
  "capability_gaps": [],
  "solution": {
    "solution_id": "uuid",
    "entry_offer": "pilot_plus_system",
    "ftl_layers": [],
    "phases": [],
    "immediate_value": "...",
    "long_term_value": "...",
    "infrastructure": {},
    "discovery_questions": [],
    "do_not_claim": []
  },
  "target": {
    "buyer_role_hypothesis_id": "uuid",
    "contact_observation_id": null,
    "contact_route_id": "uuid",
    "role": "Head of Learning and Development",
    "name": null,
    "route_type": "contact_form",
    "route_origin": "public_source",
    "route_value": "https://...",
    "route_provenance": {"source_ids": ["SRC-000004"], "human_provenance_note": null},
    "observation_status": "published_officially",
    "freshness_status": "current",
    "deliverability_status": "unknown",
    "outreach_eligibility": "eligible_after_human_review"
  },
  "ftl": {
    "knowledge_release_id": "uuid",
    "asset_match_id": "uuid",
    "positioning_claim_id": "FTL-CLM-000001",
    "selected_assets": [],
    "allowed_claims": []
  },
  "communication": {
    "language": "de",
    "channel": "contact_form",
    "tone": "professional_personal",
    "max_assets": 2,
    "auto_send_allowed": false
  },
  "prior_interactions": [],
  "stable_input_manifest": {},
  "stable_input_hash": "sha256"
}
```

## Deterministic hash correction

The packet's stable hash MUST NOT include volatile output fields.

```python
stable_manifest = {
    "manifest_schema_version": "1.0",
    "opportunity": [str(opportunity.id), opportunity.row_version],
    "company_assessment": [str(assessment.id), assessment.row_version],
    "signal_evidence": sorted(
        (str(item.id), item.content_sha256) for item in evidence
    ),
    "research_report": [str(report.id), report.content_sha256],
    "solution": [str(solution.id), solution.content_sha256],
    "target_selection": {
        "buyer_role_hypothesis_id": str(buyer_role_hypothesis.id),
        "contact_observation_id": (
            str(contact_observation.id) if contact_observation else None
        ),
        "contact_route": [str(route.id), route.row_version],
    },
    "knowledge_release": [str(release.id), release.content_sha256],
    "asset_match": [str(asset_match.id), asset_match.content_sha256],
    "assets": sorted(
        (str(asset.id), asset.content_sha256) for asset in assets
    ),
    "communication_policy": [str(policy.id), policy.content_sha256],
}
canonical = json.dumps(
    stable_manifest,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
)
stable_input_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Exclude:

```text
packet_id
generated_at
stable_input_hash itself
rendering-only fields
```

Same stable inputs return the existing packet or produce byte-equivalent payload apart from designated volatile metadata.

## Validation

Block packet creation for:

- suppressed target/company;
- missing human target selection;
- route whose origin/provenance constraints fail, whose freshness is not current, or whose outreach eligibility is not `eligible_after_human_review`; public routes require registered source evidence, while human-origin routes require an authorized user and provenance note;
- missing route legal-review state where policy requires it;
- stale required research;
- unapproved/superseded solution;
- missing source-backed signal;
- missing/stale asset-match result or confidential/archived selected assets;
- invalid language/channel;
- `auto_send_allowed=true` in initial product.

## Size and relevance

The packet is a bounded drafting context, not a database dump. Include only selected claims/evidence, compact phase summaries, no raw web page, no raw email thread, and no confidential asset content.

## Acceptance criteria

- Stable inputs yield the same stable hash.
- Packet ID/time changes do not change the stable hash.
- Material input changes create a new packet/version.
- All downstream evidence/claim/source/FTL-claim/asset refs resolve inside the packet.
- Schema serialization and canonical-hash tests pass.
