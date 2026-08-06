# 17 — FTL Knowledge, Offer, Claim, and Asset Library

**Specification version:** 2.1  
**Primary owner:** FTL editorial and product

## Purpose

Create a versioned, externally safe internal knowledge layer that allows solution design and drafting to use accurate FTL positioning, offer modules, proof points, approved claims, and confidentiality rules.

## Trust boundary

The active knowledge release is approved internal context. It MUST NOT be included in public web-research calls. It is introduced only in no-web solution design, asset matching, packet building, drafting, and review.

## Editorial source

```text
knowledge_base/
  company/
    identity.md
    positioning.md
    founders.md
    tone.md
    capabilities.json
    approved_claims.json
    prohibited_claims.json
  offers/
    *.md|json
  case_studies/
    *.md
  assets/
    assets.json
```

Sync:

```bash
python manage.py sync_ftl_knowledge --commit <git-sha> --validate
```

The command creates an immutable `KnowledgeRelease`; activation is a separate audited human action.

## OfferModuleV2

```json
{
  "key": "pilot_plus_system",
  "version": 2,
  "title": "Pilot + Production System",
  "ftl_layers": ["create", "build", "enable"],
  "problem_patterns": ["workflow", "scaling", "internal_skills"],
  "description": "Create the first premium result and the reusable workflow behind it.",
  "typical_deliverables": [],
  "suitable_client_profiles": [],
  "infrastructure_options": ["cloud", "hybrid"],
  "exclusions": [],
  "approved": true
}
```

## AssetV2

```json
{
  "asset_id": "ki_werkstatt",
  "version": 2,
  "title": "KI-Werkstatt",
  "type": "interactive_learning_environment",
  "public_url": "https://...",
  "short_description": "...",
  "detailed_description": "...",
  "capability_tags": ["learning_content", "platform", "enablement"],
  "ftl_layers": ["create", "build", "deploy", "enable"],
  "industries": ["education", "professional_services"],
  "languages": ["de", "en"],
  "confidentiality": "public|internal|confidential_client|embargoed",
  "approved_for_external_use": true,
  "status": "live|preview|archived",
  "last_reviewed_at": "ISO-8601",
  "url_last_checked_at": "ISO-8601|null"
}
```

## ApprovedClaimV2

```json
{
  "claim_key": "ftl_combines_cinematic_and_ai_engineering",
  "version": 1,
  "full_wording": "...",
  "short_wording": "...",
  "claim_type": "identity|capability|case_study_result|technical",
  "supporting_asset_ids": [],
  "allowed_audiences": ["public_business"],
  "allowed_languages": ["de", "en"],
  "paraphrase_allowed": true,
  "strengthening_prohibited": true,
  "valid_from": "YYYY-MM-DD",
  "review_due_at": "YYYY-MM-DD"
}
```

Quantitative or client-result claims require explicit supporting evidence and review. Missing evidence cannot be replaced by persuasive wording.

## Asset matching

Asset matching may use a schema-constrained no-web model, but Python filters candidates first by:

- active release;
- public/external-use approval;
- live status;
- language/audience;
- confidentiality;
- review freshness;
- valid URL.

Output:

```json
{
  "schema_version": "2.1",
  "prompt_version": "2.1.0",
  "solution_id": "uuid",
  "selected_assets": [
    {
      "asset_id": "learning_nugget_pipeline",
      "relevance_reason": "Demonstrates both immediate learning content and a reusable production workflow.",
      "priority": 1,
      "supported_solution_phase": 2
    }
  ],
  "excluded_asset_ids": [],
  "unknowns": [],
  "review_flags": []
}
```

Default maximum: two assets in first contact.

## Invalidation

A changed/withdrawn claim, confidential asset, archived URL, or new knowledge release marks dependent packets/drafts stale. It does not mutate old versions.

## Acceptance criteria

- Confidential/embargoed assets cannot enter normal drafting queries.
- Sync and activation are separate and auditable.
- Every selected asset is public, current, and relevant.
- Every FTL claim in a draft maps to an active approved claim or public asset.
- Public research never receives this private knowledge bundle.
