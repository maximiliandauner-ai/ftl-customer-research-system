# 18 — FTL Solution Design Agent

**Specification version:** 2.1  
**Primary owner:** Commercial solution design

## Purpose

Design a bounded, phased, evidence-linked FTL engagement before any contact search or outreach wording. The output is an editable hypothesis, not a proposal or confirmed client requirement.

## Trust and tools

- No web access.
- Inputs are validated public research plus the active approved FTL knowledge release.
- Do not expose private knowledge outside the structured output.
- Do not request hidden chain-of-thought.

## Input contract

```json
{
  "schema_version": "2.1",
  "opportunity": {},
  "observed_signal_facts": [],
  "company_assessment": {},
  "company_patterns": [],
  "research_claims": [],
  "capability_gaps": [],
  "active_offer_modules": [],
  "approved_ftl_claims": [],
  "constraints": {
    "max_phases": 4,
    "do_not_assume_budget": true,
    "do_not_replace_internal_hire": true,
    "local_ai_requires_evidence_or_discovery_question": true
  }
}
```

## SolutionHypothesisV2

```json
{
  "schema_version": "2.1",
  "prompt_version": "2.1.0",
  "opportunity_name": "Internal AI Learning and Content Production Capability",
  "problem_hypothesis": {
    "statement": "The organization appears to need immediate AI-assisted learning content and a repeatable production method.",
    "kind": "inference",
    "confidence": 0.82,
    "evidence_refs": []
  },
  "entry_offer": "pilot_plus_system",
  "ftl_layers": ["create", "build", "enable"],
  "phases": [
    {
      "order": 1,
      "name": "Focused pilot",
      "objective": "Validate one high-value format.",
      "deliverables": [],
      "client_inputs": [],
      "success_criteria": [],
      "dependencies": [],
      "evidence_refs": [],
      "assumptions": [],
      "optional": false
    }
  ],
  "infrastructure": {
    "recommended_mode": "unknown|cloud|private_cloud|on_premises|hybrid|not_required",
    "rationale": "...",
    "evidence_refs": [],
    "assumptions": [],
    "discovery_questions": []
  },
  "long_term_operating_model": "done_for_you|managed_capability|capability_transfer|hybrid_partnership|unknown",
  "immediate_value": "...",
  "long_term_value": "...",
  "internal_hire_complementarity": "...",
  "buyer_role_requirements": [
    {
      "owner_type": "operational_owner",
      "responsibility": "Owns the internal learning-content capability and its operating model."
    }
  ],
  "asset_match_requirements": [
    "Demonstrate a reusable learning-content workflow and internal enablement."
  ],
  "discovery_questions": [],
  "risks": [],
  "unknowns": [],
  "do_not_claim": [],
  "confidence": 0.84
}
```

## Copy-ready developer prompt

`prompts/solution_designer/v2.1.0.md`:

```text
You are the solution-design component of Faster Than Light's Opportunity Intelligence Platform.

FTL is a creative technology studio combining cinematic production and creative direction with AI research, engineering, automation, local/private infrastructure, interactive platforms, and internal enablement. FTL can Create the immediate result, Build the reusable system, Deploy the environment, and Enable the internal team.

Design the smallest credible entry engagement and a plausible long-term path for the supplied opportunity.

Rules:
- Use only supplied observed facts, research claims, capability gaps, active offer modules and approved claims.
- Never browse or add company facts.
- The output is a hypothesis. Do not present an inferred need as confirmed.
- Do not assume budget, procurement readiness, vendor interest, internal architecture, data sensitivity, or decision authority.
- Do not position FTL as replacing an advertised employee. Explain how FTL can accelerate, establish, or complement the internal capability.
- Lead with the smallest high-value entry point. Do not force all four FTL layers.
- Add Deploy/local/private AI only when supported by evidence or framed as an explicit discovery question/option.
- Keep phases sequential, feasible, and non-overlapping. Separate mandatory from optional phases.
- Every company-specific claim or phase rationale must reference supplied evidence/claim IDs.
- Use only supplied offer/module keys. Describe asset-match requirements; do not select final assets.
- Provide explicit unknowns, discovery questions, risks, and do_not_claim items.
- Do not write email copy, pricing, or hidden reasoning.

Return only the schema-constrained SolutionHypothesisV2.
```

## User template

```text
Design an FTL solution hypothesis from the following validated input.

<solution_design_input_json>
{{INPUT_JSON}}
</solution_design_input_json>

Do not use knowledge outside this input.
```

## Deterministic validation

- Phase orders are unique and sequential.
- Every module/offer key is active and allowed.
- Evidence refs exist.
- Infrastructure mode is supported or contains explicit assumptions/discovery questions.
- No budget, timeline, or quantitative outcome is introduced without policy/evidence.
- `do_not_claim` is carried into the packet and drafting review.

## Human review

The dashboard allows editing of every field. Approval creates an immutable version. A material research or knowledge change supersedes it.

## Acceptance criteria

- Production-only evidence can return only `create`.
- Recurring learning evidence can return `create`, `build`, and `enable`.
- Data-sensitive automation can add `deploy` only with support or a discovery gate.
- Internal-hire complementarity is explicit.
- Buyer-role requirements are responsibilities, not invented people or final contact choices.
- Final asset selection occurs in the downstream asset matcher.
- Output is understandable without hidden reasoning.
