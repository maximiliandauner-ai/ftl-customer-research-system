# FTL Opportunity Intelligence & Outreach System

> **Reference status — read before implementation**
>
> This file preserves the original consolidated product concept. It is **not the final normative technical specification**. Codex MUST follow `AGENTS.md`, `README.md`, `32_ARCHITECTURE_AUDIT_AND_DECISIONS.md`, and the audited subsystem files `01`–`35` when examples conflict.
>
> In particular, older examples in this reference may show superseded details such as `related_role_cluster` as a signal type, one generic email/contact verification field, contact discovery before solution design, or historical Docker/framework defaults. The audited documents separate observed signals from inferred company patterns, separate contact observation/deliverability/eligibility, use solution-informed contact discovery, use a transactional outbox, and define the current runtime/provider contracts.

## Final Python-Native Architecture and Implementation Plan

**Company:** Faster Than Light (FTL)  
**Purpose:** Discover organizations with an active need for Creative AI production, learning systems, workflow automation, internal AI capability, and local or private AI infrastructure; qualify the opportunity; research the organization; design the correct FTL engagement model; and prepare evidence-based, human-approved outreach.

---

# 1. Executive Summary

FTL should build a self-hosted commercial-intelligence platform that continuously identifies companies and institutions demonstrating an active need for capabilities that FTL can provide.

The first and most scalable source of evidence will be public job postings. A company advertising a role for AI-assisted video production, learning-content creation, AI enablement, workflow automation, creative technology, local AI systems, or related functions is publicly revealing that it is allocating attention, ownership, and resources to this capability.

The job posting is not automatically the commercial opportunity. It is the **signal**.

The commercial opportunity is the evidence-based hypothesis that FTL can help the organization:

1. produce a high-quality result for an immediate use case;
2. design and implement the reusable production or automation system behind it;
3. deploy the required infrastructure, including local or private AI environments;
4. train and enable the internal team;
5. support the organization until the capability can be operated internally;
6. continue as a creative, technical, or strategic partner where desired.

This reflects FTL’s actual positioning. FTL is not only a production company and not only a software consultancy. It combines:

- cinematic storytelling;
- filmmaking and production experience;
- creative direction;
- generative image and video production;
- AI research and engineering;
- local and cloud AI infrastructure;
- automation and agentic workflows;
- interface and platform development;
- learning environments;
- workshops and internal enablement.

The system should therefore identify not only “companies that may want content,” but organizations where FTL can create value across a longer capability journey.

The recommended stack is:

```text
Django
PostgreSQL
Celery
Redis
django-celery-beat
OpenAI Python SDK
Pydantic
httpx
selectolax or BeautifulSoup
extruct for JSON-LD
Playwright as a fallback
HTMX
Tailwind CSS
Docker Compose
```

The core operating principle is:

> **Discover broadly. Preserve the evidence. Infer the capability gap. Design the right engagement model. Research selectively. Draft precisely. Keep external communication human-approved.**

---

# 2. FTL’s Commercial Model

FTL should be represented inside the platform as a modular creative and technical partner.

## 2.1 Four layers of value

### Layer 1 — Create

FTL produces the immediate visible result.

Examples:

- cinematic AI-generated campaign content;
- generative image and video production;
- web visuals and hero films;
- branded learning content;
- learning nuggets;
- interactive educational content;
- AI characters;
- prototypes;
- product visualizations;
- websites and interactive experiences.

This is the fastest entry point because the client receives a concrete outcome.

### Layer 2 — Build

FTL creates the reusable technical and creative system behind the result.

Examples:

- automated learning-content pipelines;
- multi-agent production workflows;
- prompt and style libraries;
- content-generation interfaces;
- evaluation and validation workflows;
- automatic meeting-minute systems;
- ticket classification and labeling systems;
- retrieval and knowledge pipelines;
- internal content-production platforms;
- reusable website-generation workflows;
- API integrations;
- human-in-the-loop quality-control systems.

This turns one deliverable into a repeatable capability.

### Layer 3 — Deploy

FTL implements the required infrastructure and operating environment.

Examples:

- local AI servers;
- GPU systems;
- self-hosted models;
- private-cloud deployments;
- on-premises inference;
- secure document-processing environments;
- internal APIs;
- authentication and access control;
- monitoring;
- logging;
- model routing;
- data pipelines;
- Docker-based deployments;
- private interfaces for employees;
- hybrid local and cloud architectures.

This is particularly relevant for universities, professional-services organizations, public institutions, companies with confidential information, and organizations that want more control over data and operating costs.

### Layer 4 — Enable

FTL transfers knowledge and helps the organization operate and expand the system internally.

Examples:

- workshops;
- AI-literacy programmes;
- production playbooks;
- technical documentation;
- prompt and workflow training;
- governance guidelines;
- onboarding for internal teams;
- train-the-trainer programmes;
- handover;
- internal support;
- roadmap development;
- capability-building programmes.

The client can choose how much independence it wants. FTL can remain the production partner, operate the system jointly, or progressively transfer responsibility.

---

## 2.2 Engagement modes

The pipeline should not assume that every company needs the same offer.

### A. Done-for-you production

FTL creates the final content or experience.

Suitable when:

- the client needs a fast result;
- the use case is campaign-based;
- internal capacity is limited;
- the organization wants premium execution;
- the system does not yet need to be internalized.

### B. Pilot plus system

FTL creates the first high-quality result and simultaneously develops the reusable workflow behind it.

Suitable when:

- the organization wants to validate the use case;
- the future volume is likely to increase;
- the client needs both proof and infrastructure;
- internal ownership is emerging.

### C. Internal capability build

FTL designs and implements the complete internal pipeline, interface, knowledge layer, model setup, and operational process.

Suitable when:

- the use case is recurring;
- data sensitivity matters;
- multiple teams need access;
- the organization wants independence;
- governance and reproducibility are important.

### D. Local or private AI deployment

FTL implements the system on local machines, dedicated GPU infrastructure, private cloud, or a hybrid setup.

Suitable when:

- confidential or protected information is involved;
- the client has internal infrastructure;
- external API usage is restricted;
- recurring inference volume justifies local operation;
- the client needs control over models and data.

### E. Managed capability

FTL builds and operates the environment while the client uses it through an internal interface.

Suitable when:

- the client wants the benefits of an internal system;
- it does not yet have the technical team to maintain it;
- the client wants one accountable creative-technical partner.

### F. Capability transfer

FTL starts by operating the process and gradually transfers it to the client.

Suitable when:

- the client wants long-term independence;
- internal employees are being hired;
- the system should remain expandable;
- documentation and training are important.

### G. Fractional creative AI leadership

FTL supports the organization on a recurring basis without becoming a conventional agency retainer or full-time internal role.

Suitable when:

- the capability is still emerging;
- the organization needs senior guidance but not a full-time hire;
- multiple pilots must be coordinated;
- internal hiring is underway.

---

# 3. What the System Is Looking For

The system should search for evidence that an organization has a capability need overlapping with one or more FTL value layers.

## 3.1 The raw signal

The primary initial signal is:

> **A newly published, reposted, or materially changed public job posting whose responsibilities reveal an active organizational need that overlaps with FTL’s creative, technical, infrastructural, or enablement capabilities.**

Examples include:

- AI Video Producer;
- Generative AI Content Creator;
- Creative Technologist;
- AI Learning Content Specialist;
- Digital Learning Manager;
- AI Enablement Lead;
- Automation Engineer;
- AI Product Manager;
- AI Tutor;
- AI Content Operations;
- Knowledge Management and AI;
- Internal AI Platform Engineer;
- Prompt Engineer for communication or learning;
- AI Innovation Manager;
- Employer Branding and AI Content;
- AI Workflow Specialist;
- Applied AI Specialist;
- Generative Media Producer.

The system must also classify job descriptions whose titles are conventional but whose responsibilities are relevant.

Examples:

- an HR content role that includes AI-generated video and learning formats;
- a communications role that includes reusable prompt templates;
- a knowledge-management position that includes internal AI assistants;
- an IT role that includes local model deployment;
- a learning role that includes automatic content generation;
- a marketing role that includes scalable generative media production.

---

## 3.2 Signal versus opportunity

The architecture must maintain a strict separation:

```text
Source object
    ↓
Observed signal event
    ↓
Capability-gap assessment
    ↓
Commercial opportunity hypothesis
    ↓
Recommended FTL engagement model
```

### Source object

The original job posting, career page, announcement, or other public source.

### Signal event

The observable fact that the company created, updated, reopened, or expanded a relevant role.

### Capability-gap assessment

The structured interpretation of what the organization appears to need.

### Commercial opportunity hypothesis

A testable proposition describing where FTL may be able to help.

### Engagement model

The best combination of Create, Build, Deploy, and Enable for this organization.

The system must clearly distinguish facts from inferences.

Example:

```json
{
  "fact": "The posting requires the creation of AI-generated learning videos.",
  "inference": "The organization may benefit from a reusable learning-content production pipeline.",
  "confidence": 0.86
}
```

---

# 4. Expanded Signal Ontology

## 4.1 Creative production signal

Detected responsibilities may include:

- AI-generated video;
- generative image production;
- cinematic storytelling;
- creative direction;
- AI campaign production;
- synthetic media;
- motion design;
- AI art direction;
- visual quality control;
- post-production with generative tools;
- prompt-based visual production;
- content adaptation and localization.

Potential FTL engagement:

```text
Create
Create + Build
Managed capability
Fractional creative AI leadership
```

---

## 4.2 Learning-content signal

Detected responsibilities may include:

- e-learning production;
- digital-learning content;
- learning nuggets;
- instructional design;
- educational video;
- AI literacy;
- internal academies;
- interactive learning;
- knowledge transfer;
- AI tutors;
- training content;
- workshop material;
- curriculum development.

Potential FTL engagement:

```text
Learning-content production
Agentic learning-content pipeline
Interactive learning environment
Local knowledge system
Workshop and enablement programme
Capability transfer
```

---

## 4.3 Workflow-automation signal

Detected responsibilities may include:

- process automation;
- agentic workflows;
- automated document processing;
- automatic meeting minutes;
- ticket classification;
- content routing;
- task orchestration;
- API integration;
- internal tools;
- AI-assisted operations;
- human-in-the-loop systems;
- workflow monitoring.

Potential FTL engagement:

```text
Workflow audit
Prototype
Internal automation platform
Local or private deployment
Managed workflow
Capability transfer
```

---

## 4.4 Internal AI enablement signal

Detected responsibilities may include:

- employee AI training;
- internal workshops;
- AI adoption;
- use-case identification;
- prompt libraries;
- guidelines;
- AI governance;
- tool evaluation;
- best-practice development;
- internal communities;
- change management;
- responsible AI use.

Potential FTL engagement:

```text
Enablement programme
Workshop series
Internal tool interface
AI playbook
Use-case portfolio
Train-the-trainer programme
```

---

## 4.5 Local and private AI infrastructure signal

Detected responsibilities may include:

- self-hosted models;
- on-premises inference;
- private AI;
- GPU servers;
- model serving;
- secure document processing;
- internal APIs;
- confidential data;
- data-sovereign AI;
- model evaluation;
- inference optimization;
- local RAG;
- containerized deployment;
- private knowledge assistants.

Potential FTL engagement:

```text
Infrastructure assessment
Local AI architecture
Private deployment
Internal model platform
Secure workflow implementation
Monitoring and documentation
Technical handover
```

---

## 4.6 Creative automation and content operations signal

Detected responsibilities may include:

- scalable content production;
- automated asset generation;
- localization;
- templated campaign systems;
- prompt templates;
- production pipelines;
- brand consistency;
- generative content operations;
- quality-control automation;
- asset management.

Potential FTL engagement:

```text
Brand-controlled generation system
Reusable production platform
Automated evaluation layer
Content-production interface
Managed system
Internal enablement
```

---

## 4.7 Innovation and experimentation signal

Detected responsibilities may include:

- prototyping;
- AI pilots;
- innovation labs;
- emerging-technology research;
- tool benchmarking;
- proof-of-concept development;
- experimental formats;
- research transfer;
- internal innovation programmes.

Potential FTL engagement:

```text
Discovery workshop
Pilot
Applied AI research project
Interactive demonstrator
Technical prototype
Strategic roadmap
```

---

## 4.8 Intelligent-product and physical-AI storytelling signal

Detected responsibilities may include:

- intelligent vehicles;
- robotics;
- physical AI;
- smart products;
- future mobility;
- technical product communication;
- human-machine interaction;
- AI characters;
- digital twins;
- immersive product experiences.

Potential FTL engagement:

```text
Cinematic product narrative
Interactive experience
AI character
Product visualization
Campaign system
Technical demonstrator
```

---

# 5. Capability-Gap Classification

Every relevant signal should be translated into one or more capability gaps.

```text
CONTENT_GAP
PRODUCTION_CAPACITY_GAP
CREATIVE_DIRECTION_GAP
WORKFLOW_GAP
PLATFORM_GAP
INFRASTRUCTURE_GAP
LOCAL_AI_GAP
DATA_GOVERNANCE_GAP
INTERNAL_SKILLS_GAP
ADOPTION_GAP
QUALITY_CONTROL_GAP
SCALING_GAP
OWNERSHIP_GAP
EXPERIMENTATION_GAP
```

## Example

A working-student role for AI-assisted learning-video production may reveal:

```json
{
  "capability_gaps": [
    {
      "type": "CONTENT_GAP",
      "confidence": 0.96,
      "evidence": ["Create AI-generated learning videos"]
    },
    {
      "type": "WORKFLOW_GAP",
      "confidence": 0.78,
      "evidence": ["Develop prompts and evaluate tools"]
    },
    {
      "type": "INTERNAL_SKILLS_GAP",
      "confidence": 0.66,
      "evidence": ["Research AI and digital-learning trends"]
    }
  ]
}
```

The platform should then produce a solution hypothesis:

```json
{
  "recommended_ftl_layers": [
    "CREATE",
    "BUILD",
    "ENABLE"
  ],
  "recommended_entry_offer": "pilot_plus_system",
  "long_term_path": "capability_transfer",
  "infrastructure_option": "cloud_first_with_private_extension"
}
```

---

# 6. Commercial Interpretation of Hiring Signals

## 6.1 Why a job posting matters

A relevant posting can indicate:

- explicit operational need;
- approved headcount;
- allocated budget;
- internal ownership;
- urgency;
- capability-building;
- a new strategic initiative;
- a recurring production requirement;
- a gap between ambition and current execution capacity.

However, it does not prove that the organization wants an external vendor.

The platform must therefore estimate both **capability relevance** and **commercial actionability**.

---

## 6.2 Capability relevance

This measures how strongly the observed need overlaps with FTL.

Recommended components:

```text
Task overlap                         25%
FTL capability overlap               20%
Potential for reusable systems       15%
Potential for infrastructure work    10%
Potential for internal enablement    10%
Portfolio proof availability         10%
Industry and strategic relevance     10%
```

---

## 6.3 Commercial actionability

This measures whether there is a credible reason to approach the organization now.

Recommended components:

```text
Signal recency                       15%
Organizational commitment            15%
Problem clarity                      15%
Vendor or partner receptivity        15%
Potential for hybrid delivery        10%
Owner clarity                        10%
Contactability                       10%
Budget proxy                          5%
Additional corroborating signals      5%
```

---

## 6.4 Long-term system potential

This measures whether the opportunity could expand beyond a one-off deliverable.

Recommended components:

```text
Recurring use-case potential         20%
Number of users or departments       15%
Content or workflow volume           15%
Need for reproducibility             10%
Need for governance                  10%
Need for local or private systems    10%
Potential for capability transfer    10%
Potential for continued partnership  10%
```

---

## 6.5 Strategic value

This measures the broader importance to FTL.

Recommended components:

```text
Brand and reputation fit
Case-study potential
International relevance
Creative ambition
Technical depth
Long-term relationship potential
Market adjacency
Portfolio differentiation
```

---

## 6.6 Priority formula

An initial formula can be:

```text
priority_score =
    0.40 × capability_relevance
  + 0.25 × commercial_actionability
  + 0.20 × long_term_system_potential
  + 0.15 × strategic_value
```

Store every component separately. Do not store only one opaque number.

---

# 7. Vendor-Receptivity and Hybrid-Opportunity Assessment

## Positive indicators

- freelance or contract structure;
- project-based language;
- collaboration with agencies or production partners;
- responsibility for vendor selection;
- responsibility for tool and workflow selection;
- creation of a new function;
- responsibility for documentation or standards;
- pilot development;
- workshop delivery;
- internal enablement;
- change management;
- unusually broad responsibilities for one role;
- immediate start;
- multiple related openings;
- repeated reposting;
- a junior role expected to establish an entire capability;
- temporary capacity shortage;
- internal team still being assembled.

## Neutral indicators

- standard permanent employment;
- an established internal team;
- general AI responsibilities;
- cross-functional coordination;
- strategic responsibility without partner language.

## Negative or caution indicators

- narrow execution-only role;
- highly mature internal AI studio;
- explicit exclusion of external vendors;
- highly regulated environment without a suitable contact route;
- no evidence of recurring need;
- stale or closed role;
- third-party recruitment listing without a verified employer source.

The classification should support:

```text
high
medium
low
unknown
```

Missing information must remain `unknown`.

---

# 8. Interpreting Junior, Internship, and Working-Student Positions

Junior roles can be commercially valuable signals even when their salary budget is limited.

They may indicate:

- experimentation has started;
- the organization recognizes the need;
- the operating model is immature;
- no reusable system exists;
- ownership is fragmented;
- a small internal team needs a foundation;
- the company is trying to cover a broad capability with limited headcount.

The recommended FTL entry point should therefore be appropriately scoped.

Suitable offers include:

- a focused pilot;
- a production-system audit;
- a tool evaluation;
- a reusable workflow;
- a first learning-content format;
- a local AI proof of concept;
- a prompt and quality framework;
- onboarding and training for the future internal employee;
- a fractional Creative AI Producer or Technical AI Lead engagement.

The outreach should not imply that FTL wants to replace the advertised employee.

Prefer:

> FTL can help establish the creative and technical environment in which the internal role becomes productive, scalable, and sustainable.

---

# 9. Example: HOFFMANN EITLE

## 9.1 Observed signal

The supplied role indicates a need for:

- AI-generated video;
- prompt development for scripts, voice, and video;
- format conception;
- tool evaluation;
- research into AI and digital-learning trends;
- an internal HR, communication, or learning context.

## 9.2 Capability gaps

Potential gaps include:

```text
CONTENT_GAP
WORKFLOW_GAP
TOOL_EVALUATION_GAP
QUALITY_CONTROL_GAP
INTERNAL_SKILLS_GAP
SCALING_GAP
```

## 9.3 Recommended FTL entry offer

```text
Pilot plus system
```

Possible first engagement:

1. define one high-value learning or communication format;
2. produce the first cinematic AI-assisted content;
3. document the creative and technical workflow;
4. create prompt and style templates;
5. evaluate suitable image, video, voice, and editing tools;
6. introduce quality and review criteria;
7. build a lightweight internal interface where useful;
8. train the internal team;
9. provide a roadmap for further formats.

## 9.4 Long-term path

```text
Create
    ↓
Build
    ↓
Deploy
    ↓
Enable
    ↓
Optional capability transfer or managed partnership
```

## 9.5 Relevant FTL proof points

The system should be able to select from:

- KI-Werkstatt;
- interactive learning environments;
- agentic Learning Nugget production pipeline;
- automatic meeting-minute workflows;
- automated ticket labeling;
- local AI interfaces;
- AI server and infrastructure work;
- cinematic generative image and video projects;
- complete webpage production;
- creative direction and film-production experience.

---

# 10. Fully Python-Native Architecture

## 10.1 Recommended stack

```text
Backend and server-rendered application:
- Django

Database:
- PostgreSQL

Task queue:
- Celery

Task broker and caching:
- Redis

Scheduling:
- django-celery-beat

Data validation:
- Pydantic

AI:
- OpenAI Python SDK

HTTP retrieval:
- httpx

HTML parsing:
- selectolax or BeautifulSoup

Structured data:
- extruct

Browser fallback:
- Playwright

Frontend:
- Django templates
- HTMX
- Tailwind CSS

Deployment:
- Docker Compose
- Nginx or Caddy
```

## 10.2 Why Django

Django provides:

- authentication;
- permissions;
- ORM;
- migrations;
- forms;
- server-rendered interfaces;
- administration;
- session management;
- mature security defaults;
- strong support for relational workflows.

The built-in administration interface can be used for data inspection and operational debugging. The final FTL dashboard can use custom Django templates and HTMX.

## 10.3 Why Celery

Research, crawling, classification, enrichment, and drafting need:

- retries;
- task states;
- queue separation;
- concurrency controls;
- scheduling;
- rate limiting;
- failure visibility;
- restart resilience.

Recommended queues:

```text
discovery
fetch
parse
classification
aggregation
research
deep_research
contact_enrichment
solution_design
drafting
notifications
maintenance
```

## 10.4 Docker services

```text
web
worker-discovery
worker-ai
worker-research
celery-beat
postgres
redis
reverse-proxy
```

Use the same application image for the workers, with queue-specific startup commands.

---

# 11. Discovery Architecture

## Layer 1 — Search discovery

Use web search to identify:

- relevant job postings;
- unknown companies;
- career pages;
- ATS pages;
- related AI initiatives;
- capability announcements;
- company-specific transformation signals.

Example search families:

```text
"AI Video Producer" Germany
"Generative AI Content" jobs
"KI Videoproduktion" Karriere
"AI Learning Content" jobs
"Digital Learning" "Generative AI"
"Creative Technologist" AI
"AI Enablement" jobs
"AI Academy" content
"Prompt" "Runway" job
"ComfyUI" careers
"local LLM" jobs
"private AI" careers
"AI automation" internal tools
"meeting minutes" AI automation
"knowledge management" generative AI
```

ATS-specific queries:

```text
site:jobs.personio.de
site:boards.greenhouse.io
site:jobs.lever.co
site:jobs.ashbyhq.com
```

Store search definitions in PostgreSQL.

Fields:

```text
id
name
query
language
region
positive_terms
negative_terms
source_domains
target_capabilities
active
schedule
last_run_at
result_count
qualified_count
performance_score
```

---

## Layer 2 — Direct ATS ingestion

Once a company’s ATS is known, use an adapter instead of rediscovering every posting.

Adapters:

```text
PersonioAdapter
GreenhouseAdapter
LeverAdapter
AshbyAdapter
GenericJsonLdAdapter
GenericHtmlAdapter
```

Every adapter returns the same normalized Pydantic model.

---

## Layer 3 — JobPosting JSON-LD

For generic career pages:

1. retrieve the page;
2. extract JSON-LD;
3. find objects with `@type = JobPosting`;
4. normalize the fields;
5. preserve the source payload;
6. fall back to HTML parsing when needed.

---

## Layer 4 — Sitemap and career-page monitoring

For known companies without a supported ATS:

- inspect `robots.txt`;
- inspect sitemap files;
- detect career-related URLs;
- track newly added URLs;
- use `lastmod` as a weak change indicator;
- compare content hashes;
- fetch only changed pages.

---

## Layer 5 — Browser fallback

Use Playwright only when:

- the page is entirely JavaScript-rendered;
- normal retrieval does not expose the content;
- structured data is absent;
- interaction is required.

Browser automation should remain a fallback because it is slower and more fragile.

---

# 12. Normalized Models

## 12.1 Job posting

```python
class NormalizedJobPosting(BaseModel):
    external_id: str | None
    source_type: str
    source_url: str
    canonical_url: str

    company_name: str
    company_domain: str | None

    title: str
    department: str | None
    locations: list[str]
    remote_type: str | None
    employment_type: str | None
    seniority: str | None

    published_at: datetime | None
    updated_at: datetime | None
    valid_through: datetime | None
    observed_at: datetime

    description_text: str
    description_html: str | None

    language: str | None
    source_payload: dict

    content_hash: str
```

## 12.2 Signal event

```python
class SignalEvent(BaseModel):
    id: UUID
    company_id: UUID
    job_posting_id: UUID

    signal_type: Literal[
        "capability_hiring",
        "related_role_cluster",
        "role_reposted",
        "material_description_change",
        "role_closed"
    ]

    event_kind: Literal[
        "created",
        "updated",
        "reopened",
        "aggregated",
        "closed"
    ]

    occurred_at: datetime | None
    observed_at: datetime

    capability_tags: list[str]
    evidence_spans: list[str]

    source_confidence: float
    extraction_confidence: float
    deduplication_key: str
```

## 12.3 Capability-gap assessment

```python
class CapabilityGap(BaseModel):
    gap_type: Literal[
        "content",
        "production_capacity",
        "creative_direction",
        "workflow",
        "platform",
        "infrastructure",
        "local_ai",
        "data_governance",
        "internal_skills",
        "adoption",
        "quality_control",
        "scaling",
        "ownership",
        "experimentation"
    ]
    confidence: float
    evidence: list[str]
    rationale: str
```

## 12.4 Solution hypothesis

```python
class SolutionHypothesis(BaseModel):
    recommended_ftl_layers: list[
        Literal["create", "build", "deploy", "enable"]
    ]

    entry_offer: Literal[
        "done_for_you",
        "pilot",
        "pilot_plus_system",
        "workflow_audit",
        "internal_capability_build",
        "local_ai_assessment",
        "managed_capability",
        "capability_transfer",
        "fractional_leadership"
    ]

    long_term_path: str
    infrastructure_option: Literal[
        "not_required",
        "cloud",
        "private_cloud",
        "on_premises",
        "hybrid",
        "unknown"
    ]

    immediate_value: str
    long_term_value: str
    likely_client_owner_roles: list[str]
    risks: list[str]
    confidence: float
```

---

# 13. Snapshotting and Material-Change Detection

Store immutable snapshots:

```text
job_posting
    └── job_posting_snapshot
            ├── fetched_at
            ├── content_hash
            ├── normalized_text
            ├── raw_payload
            ├── change_summary
            └── is_material_change
```

On retrieval:

1. compare external identifiers;
2. compare canonical URL;
3. compare content hashes;
4. compare normalized descriptions;
5. identify changed sections;
6. calculate semantic similarity;
7. classify the change.

Material changes include:

- new AI responsibilities;
- new system-building responsibility;
- local or private AI requirements;
- new workshop or enablement tasks;
- added ownership;
- seniority changes;
- change in contract type;
- location changes;
- role reopening;
- substantial rewriting.

Formatting changes should not generate a new opportunity.

---

# 14. Deduplication

Use layered deduplication:

```text
1. ATS provider + external job ID
2. Canonical URL
3. Company domain + normalized title + location
4. Content hash
5. Semantic similarity
```

The first-party source should normally be authoritative.

Store duplicate relationships rather than deleting all secondary records. Secondary sources may contain additional metadata.

---

# 15. Classification Pipeline

## Stage A — Deterministic prefilter

Remove obvious noise:

- unrelated AI research jobs;
- pure backend engineering without relevant use cases;
- generic data-science positions;
- expired postings;
- unsupported regions where relevant;
- duplicate postings;
- blocked companies;
- excluded industries.

Do not rely only on title keywords.

---

## Stage B — Structured LLM classification

The classifier receives the normalized posting and returns schema-valid output.

Example:

```json
{
  "is_ftl_relevant": true,
  "relevance_confidence": 0.94,
  "capability_clusters": [
    "creative_ai_production",
    "learning_content",
    "workflow_automation",
    "internal_enablement"
  ],
  "explicit_evidence": [
    {
      "text": "Develop AI-generated learning-video formats",
      "capability": "learning_content"
    }
  ],
  "capability_gaps": [
    {
      "type": "workflow",
      "confidence": 0.82,
      "evidence": [
        "Evaluate tools and develop prompts"
      ]
    }
  ],
  "recommended_ftl_layers": [
    "create",
    "build",
    "enable"
  ],
  "recommended_entry_offer": "pilot_plus_system",
  "infrastructure_option": "unknown",
  "employment_only_probability": 0.28,
  "external_service_probability": 0.58,
  "hybrid_probability": 0.79,
  "capability_relevance": 92,
  "commercial_actionability": 64,
  "long_term_system_potential": 84,
  "strategic_value": 77,
  "priority_score": 81
}
```

---

## Stage C — Company aggregation

Aggregate all relevant signals for one company.

Features:

```text
related_roles_open
related_roles_added_30d
related_roles_added_90d
related_roles_closed_90d
roles_reposted
departments_involved
capability_cluster_count
seniority_distribution
average_role_relevance
highest_role_relevance
infrastructure_signal_count
enablement_signal_count
signal_recency
```

Example interpretation:

```text
One relevant junior role:
Moderate capability signal

Several related roles across learning, IT, and communications:
Strong cross-functional capability-building signal

Senior owner plus multiple execution roles:
Strong organizational commitment and likely long-term system potential
```

---

# 16. Research Tiers

## Tier 0 — Source retrieval

Used for all source records.

Tasks:

- fetch;
- parse;
- normalize;
- snapshot;
- deduplicate.

No research model required.

## Tier 1 — Signal classification

Used for every potentially relevant posting.

Produces:

- capability clusters;
- evidence;
- capability gaps;
- relevance score;
- actionability score;
- long-term potential;
- initial solution hypothesis.

## Tier 2 — Lightweight company research

Used above a configurable threshold.

Research:

- company offering;
- industry;
- locations;
- approximate size;
- current AI initiatives;
- learning programmes;
- content activities;
- local or private AI context;
- relevant departments;
- related openings;
- likely buyer roles;
- public contact routes.

## Tier 3 — Agentic opportunity research

Used for stronger companies.

Research:

- strategic context;
- why the capability matters now;
- likely internal owner;
- likely objections;
- current vendors or partners;
- applicable FTL proof points;
- appropriate engagement mode;
- recommended first approach.

## Tier 4 — Deep research

Reserved for:

- strategically important accounts;
- companies with multiple high-value signals;
- manually selected organizations;
- complex institutions;
- proposal preparation;
- major local-infrastructure opportunities.

Deep research should not be the default discovery mechanism.

---

# 17. FTL Solution-Design Pipeline

After research, a dedicated agent should design the engagement rather than immediately drafting an email.

## Inputs

```text
Company profile
Signals
Capability gaps
Company-level pattern
Research findings
Potential buyer roles
FTL offer modules
FTL proof points
Infrastructure constraints
Strategic value
```

## Outputs

```json
{
  "opportunity_name": "Internal AI Learning and Content Production Capability",
  "problem_hypothesis": "...",
  "recommended_entry_offer": "pilot_plus_system",
  "ftl_layers": [
    "create",
    "build",
    "enable"
  ],
  "phase_1": {
    "name": "Pilot",
    "outcome": "...",
    "deliverables": []
  },
  "phase_2": {
    "name": "Reusable production system",
    "outcome": "...",
    "deliverables": []
  },
  "phase_3": {
    "name": "Internal deployment and enablement",
    "outcome": "...",
    "deliverables": []
  },
  "long_term_operating_model": "capability_transfer",
  "infrastructure_recommendation": "hybrid",
  "selected_ftl_assets": [],
  "buyer_roles": [],
  "risks": [],
  "confidence": 0.84
}
```

This separation ensures that outreach is based on a coherent commercial concept.

---

# 18. PostgreSQL Data Model

## `companies`

```text
id
name
normalized_name
primary_domain
linkedin_url
headquarters
locations
industry
employee_range
company_type
description
strategic_fit
created_at
updated_at
```

## `job_sources`

```text
id
source_type
base_url
ats_provider
company_id
active
last_success_at
failure_count
metadata
```

## `job_postings`

```text
id
company_id
source_id
external_id
canonical_url
title
department
employment_type
seniority
published_at
updated_at
valid_through
first_seen_at
last_seen_at
current_status
content_hash
normalized_text
raw_payload
```

## `job_posting_snapshots`

```text
id
job_posting_id
fetched_at
content_hash
normalized_text
raw_payload
change_summary
is_material_change
```

## `signal_events`

```text
id
company_id
job_posting_id
signal_type
event_kind
occurred_at
observed_at
capability_tags
evidence_spans
confidence
deduplication_key
```

## `signal_assessments`

```text
id
signal_event_id
classifier_version
prompt_version
model
capability_relevance
commercial_actionability
long_term_system_potential
strategic_value
vendor_receptivity
problem_clarity
urgency
budget_proxy
owner_clarity
contactability
recommended_ftl_layers
recommended_entry_offer
structured_output
created_at
```

## `capability_gaps`

```text
id
signal_assessment_id
gap_type
confidence
evidence
rationale
```

## `opportunities`

```text
id
company_id
title
primary_signal_id
status
owner_id
priority_score
opportunity_type
primary_use_case
entry_offer
long_term_operating_model
infrastructure_option
qualification_status
outreach_status
next_action
next_action_at
created_at
updated_at
```

## `opportunity_signals`

```text
opportunity_id
signal_event_id
relationship_type
```

## `solution_hypotheses`

```text
id
opportunity_id
version
problem_hypothesis
recommended_ftl_layers
entry_offer
phase_plan
long_term_path
infrastructure_recommendation
buyer_roles
risks
confidence
created_at
```

## `research_runs`

```text
id
opportunity_id
research_type
status
provider
model
prompt_version
external_response_id
started_at
completed_at
cost_metadata
report_markdown
structured_result
error
```

## `research_sources`

```text
id
research_run_id
url
source_title
publisher
retrieved_at
source_type
claim_support
confidence
```

## `contacts`

```text
id
company_id
name
role
department
seniority
email
email_status
profile_url
source_url
retrieved_at
contact_route
is_decision_maker
is_suppressed
```

## `ftl_offer_modules`

```text
id
name
layer
description
suitable_capability_gaps
suitable_industries
infrastructure_requirements
deliverables
approved
version
```

## `assets`

```text
id
title
asset_type
url
short_description
detailed_description
capabilities
industries
ftl_layers
languages
confidentiality_status
approved_for_external_use
publication_status
last_reviewed_at
```

## `outreach_drafts`

```text
id
opportunity_id
contact_id
solution_hypothesis_id
channel
language
subject
body
draft_version
prompt_version
selected_asset_ids
factual_review_status
human_approval_status
created_by
created_at
```

## `interactions`

```text
id
opportunity_id
contact_id
channel
direction
external_message_id
thread_id
sent_at
received_at
subject
body
reply_classification
next_action
```

## `search_definitions`

```text
id
name
query
language
region
target_capabilities
positive_terms
negative_terms
source_domains
active
schedule
last_run_at
performance_metrics
```

## `pipeline_runs`

```text
id
pipeline_name
task_id
status
started_at
completed_at
input_count
output_count
error_count
cost_metadata
logs
```

## `suppression_list`

```text
id
company_id
contact_id
reason
created_at
created_by
```

---

# 19. Workflow States

## Research status

```text
new
queued
classifying
classified
research_queued
researching
research_complete
research_failed
```

## Qualification status

```text
unreviewed
qualified
watchlist
employment_only
hybrid_opportunity
service_opportunity
rejected
duplicate
expired
```

## Solution status

```text
not_started
drafted
under_review
approved
needs_revision
```

## Outreach status

```text
not_started
strategy_ready
draft_ready
needs_revision
approved
sent
follow_up_due
replied
closed
do_not_contact
```

## Relationship stage

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

---

# 20. Internal Dashboard

## 20.1 Daily signal inbox

Display:

- company;
- role;
- location;
- publication date;
- source;
- evidence excerpts;
- capability clusters;
- capability gaps;
- FTL layers;
- relevance;
- actionability;
- long-term potential;
- priority;
- state.

Actions:

```text
Qualify
Reject
Watch
Research
Create opportunity
Assign owner
Open source
```

## 20.2 Company page

Display:

- company overview;
- all job postings;
- signal timeline;
- capability heatmap;
- related departments;
- opportunity hypotheses;
- contacts;
- research;
- drafts;
- interactions;
- outcome history.

## 20.3 Opportunity page

Display:

- problem hypothesis;
- evidence;
- capability gaps;
- recommended engagement mode;
- Create / Build / Deploy / Enable layers;
- phased solution;
- infrastructure recommendation;
- selected FTL assets;
- buyer roles;
- risks;
- next action.

## 20.4 Research workspace

Display:

- active research tasks;
- sources;
- claims;
- citations;
- Markdown report;
- structured output;
- model;
- prompt version;
- cost;
- errors.

## 20.5 Solution designer

Allow human editing of:

- entry offer;
- FTL layers;
- phased plan;
- infrastructure mode;
- long-term operating model;
- assets;
- buyer roles;
- risks.

## 20.6 Outreach workspace

Display:

- outreach rationale;
- recommended route;
- subject options;
- email;
- shorter message;
- selected resources;
- factual flags;
- approval controls.

## 20.7 Search-definition page

Manage:

- queries;
- capability clusters;
- positive terms;
- negative terms;
- languages;
- countries;
- source domains;
- schedule;
- status.

## 20.8 FTL knowledge and asset library

Manage:

- company identity;
- positioning;
- capabilities;
- offer modules;
- approved claims;
- projects;
- case studies;
- portfolio links;
- confidentiality;
- external-use approval.

## 20.9 Infrastructure and operations

Display:

- worker queues;
- scheduled jobs;
- failed tasks;
- retry controls;
- API usage;
- model usage;
- cost;
- retrieval statistics;
- parsing failures;
- source health.

## 20.10 Analytics

Track:

- discovered jobs;
- relevant signals;
- qualified companies;
- opportunity types;
- FTL layers requested;
- long-term system potential;
- local-AI opportunities;
- drafts approved;
- messages sent;
- replies;
- meetings;
- proposals;
- wins;
- outcomes by signal type;
- outcomes by engagement model.

---

# 21. FTL Knowledge Layer

Store stable information in version-controlled Markdown and JSON.

```text
knowledge/
  company/
    identity.md
    positioning.md
    founders.md
    capabilities.json
    industries.json
    tone.md
    approved_claims.md
    prohibited_claims.md

  offers/
    done_for_you_production.md
    cinematic_ai_pilot.md
    pilot_plus_system.md
    creative_ai_production_system.md
    learning_environment.md
    learning_content_pipeline.md
    workflow_automation.md
    local_ai_infrastructure.md
    private_ai_platform.md
    workshop_and_enablement.md
    capability_transfer.md
    fractional_creative_ai_leadership.md

  assets/
    assets.json

  case_studies/
    ki_werkstatt.md
    learning_nugget_pipeline.md
    meeting_minutes.md
    ticket_labeling.md
    local_ai_interfaces.md
    infrastructure_and_servers.md
    website_and_visual_production.md
    cinematic_ai_projects.md
```

Every research report, solution hypothesis, and outreach draft should store the active knowledge version or Git commit.

---

# 22. Opportunity Packet

The drafting pipeline should receive a compact JSON packet.

```json
{
  "schema_version": "1.0",
  "company": {},
  "signals": [],
  "evidence": [],
  "capability_gaps": [],
  "company_context": {},
  "commercial_assessment": {},
  "solution_hypothesis": {
    "entry_offer": "",
    "ftl_layers": [],
    "phases": [],
    "long_term_path": "",
    "infrastructure_option": ""
  },
  "contacts": [],
  "selected_ftl_assets": [],
  "communication_constraints": {},
  "prior_interactions": []
}
```

The database remains the source of truth. JSON is the LLM exchange format. Markdown is the human-readable research format.

---

# 23. Outreach Pipeline

## 23.1 Research first

The outreach generator must not invent the company’s need.

It should use:

- exact signal evidence;
- company research;
- capability-gap assessment;
- solution hypothesis;
- verified contact information;
- approved FTL assets.

## 23.2 Message structure

The message should:

1. begin with a specific observation;
2. explain the broader capability implication carefully;
3. introduce FTL in one precise sentence;
4. describe the most relevant entry offer;
5. show the longer-term possibility without overselling;
6. include one or two proof points;
7. propose a low-friction next step.

## 23.3 Positioning language

FTL should not appear as a generic AI agency.

A suitable formulation is:

> Faster Than Light combines cinematic production and creative direction with AI research, engineering, automation, and infrastructure development. We can create the first visible result, build the reusable system behind it, and enable internal teams to operate and expand the capability themselves.

## 23.4 Avoid replacement framing

Do not write:

> We can do the work instead of the person you are hiring.

Prefer:

> Your current hiring activity suggests that this capability is becoming strategically relevant. FTL can help establish the creative, technical, and operational foundation around it—from a first high-quality pilot to the internal workflows, infrastructure, and training needed to scale it.

## 23.5 Structured output

```json
{
  "recommended_channel": "email",
  "language": "de",
  "angle": "",
  "subject_options": [],
  "email_body": "",
  "short_message": "",
  "selected_asset_ids": [],
  "claims_requiring_review": [],
  "suggested_follow_up": "",
  "confidence": 0.86
}
```

---

# 24. Human Approval

Initially:

```text
No automatic first-contact sending.
```

The system may automatically:

- discover;
- fetch;
- parse;
- classify;
- aggregate;
- research;
- identify possible roles;
- create solution hypotheses;
- select proof points;
- draft messages;
- create email drafts;
- schedule internal follow-up tasks.

A founder should approve:

- the company;
- the opportunity;
- the solution hypothesis;
- the contact;
- the route;
- the selected resources;
- the final message;
- the send action.

---

# 25. Daily Workflow

## 25.1 Scheduled discovery

Run once daily in `Europe/Berlin`.

1. load active search definitions;
2. fetch known ATS sources;
3. monitor known career pages;
4. run targeted discovery searches;
5. normalize source objects;
6. create snapshots;
7. deduplicate;
8. detect new and changed postings;
9. create signal events;
10. queue relevant records for classification.

## 25.2 Classification

1. run deterministic prefilters;
2. extract capability evidence;
3. classify capability clusters;
4. identify capability gaps;
5. calculate scores;
6. recommend FTL layers;
7. recommend an entry offer;
8. estimate long-term system potential;
9. route the record.

## 25.3 Aggregation

1. group signals by company domain;
2. detect related roles;
3. calculate hiring momentum;
4. identify cross-department patterns;
5. create or update company opportunities.

## 25.4 Research

1. build a precise research brief;
2. research the company;
3. identify likely owners;
4. investigate current initiatives;
5. identify infrastructure and governance context;
6. create a structured research result;
7. preserve citations;
8. update the opportunity.

## 25.5 Solution design

1. identify the best entry offer;
2. select Create / Build / Deploy / Enable layers;
3. design the phased path;
4. determine infrastructure options;
5. select FTL proof points;
6. identify risks;
7. send the hypothesis to human review.

## 25.6 Outreach

1. identify a legitimate contact route;
2. generate the tailored message;
3. run factual checks;
4. create a draft;
5. request approval;
6. record the interaction;
7. monitor replies and follow-ups.

---

# 26. Evaluation

Create a manually labeled dataset.

Each record should contain:

```text
ftl_relevant
capability_clusters
capability_gaps
commercially_actionable
employment_only
hybrid_opportunity
best_entry_offer
recommended_ftl_layers
long_term_system_potential
infrastructure_relevance
priority
rejection_reason
```

Track:

- precision among top-ranked companies;
- recall on known good examples;
- duplicate rate;
- evidence accuracy;
- company-aggregation quality;
- capability-gap accuracy;
- solution-hypothesis acceptance;
- draft acceptance;
- reply rate;
- meeting rate;
- proposal rate;
- win rate;
- outcomes by signal category;
- outcomes by engagement model;
- research cost per qualified opportunity.

Once enough outcomes exist, train an interpretable ranking model using historical features.

Start with:

```text
Logistic regression
Gradient-boosted trees
Learning-to-rank baseline
```

Potential features:

```text
role embedding
company features
signal recency
related-role count
departments involved
seniority
capability gaps
vendor receptivity
long-term system potential
infrastructure relevance
offer shape
contactability
historical outcomes
```

---

# 27. Repository Structure

```text
ftl-opportunity-radar/
  README.md

  docs/
    architecture.md
    data-model.md
    signal-ontology.md
    opportunity-model.md
    compliance.md
    operations.md

  config/
    capabilities.yaml
    scoring.yaml
    search_definitions.yaml
    exclusion_rules.yaml

  schemas/
    job_posting.py
    signal.py
    capability_gap.py
    research.py
    solution_hypothesis.py
    opportunity_packet.py
    outreach.py

  apps/
    companies/
    sources/
    jobs/
    signals/
    opportunities/
    research/
    solutions/
    contacts/
    outreach/
    interactions/
    assets/
    analytics/
    operations/

  connectors/
    openai_search/
    personio/
    greenhouse/
    lever/
    ashby/
    jsonld/
    generic_html/
    playwright/

  tasks/
    discovery.py
    fetching.py
    parsing.py
    classification.py
    aggregation.py
    research.py
    deep_research.py
    solution_design.py
    drafting.py
    notifications.py
    maintenance.py

  prompts/
    classifier.md
    company_research.md
    opportunity_research.md
    capability_gap_analyzer.md
    solution_designer.md
    asset_matcher.md
    outreach_writer.md
    factual_reviewer.md

  knowledge/
    company/
    offers/
    assets/
    case_studies/

  templates/
  static/
  tests/
    fixtures/
    evaluation/
    integration/

  docker/
  docker-compose.yml
  .env.example
```

---

# 28. Implementation Roadmap

## Phase 1 — FTL ontology and calibration

- define capability clusters;
- define capability gaps;
- define FTL value layers;
- define engagement modes;
- define offer modules;
- create positive and negative examples;
- label representative job postings;
- establish scoring.

## Phase 2 — Core platform

- Django;
- PostgreSQL;
- authentication;
- permissions;
- Celery;
- Redis;
- Docker;
- base dashboard;
- pipeline-run logging.

## Phase 3 — Discovery and normalization

- search discovery;
- Personio adapter;
- Greenhouse adapter;
- Lever adapter;
- Ashby adapter;
- JSON-LD parser;
- HTML parser;
- snapshots;
- material-change detection;
- deduplication.

## Phase 4 — Signal intelligence

- deterministic prefilter;
- structured classifier;
- evidence extraction;
- capability-gap detection;
- score calculation;
- company aggregation;
- evaluation interface.

## Phase 5 — Research

- company research;
- opportunity research;
- source storage;
- deep-research jobs;
- asynchronous completion;
- research dashboard.

## Phase 6 — Solution design

- offer-module library;
- FTL-layer selection;
- phased solution generation;
- infrastructure recommendation;
- asset matching;
- human review.

## Phase 7 — Outreach

- contact-route research;
- structured draft generation;
- factual review;
- email-draft integration;
- approval workflow;
- interaction history.

## Phase 8 — Learning loop

- analytics;
- rejection analysis;
- prompt evaluation;
- score calibration;
- outcome-based ranking;
- search-query performance;
- new signal categories.

---

# 29. Final System Architecture

```text
                        PUBLIC JOB AND COMPANY SOURCES
                                      │
               Search · ATS feeds · JSON-LD · Career pages
                                      │
                                      ▼
                         PYTHON DISCOVERY LAYER
                                      │
                     Fetch · Parse · Normalize · Snapshot
                                      │
                                      ▼
                            RAW SOURCE RECORDS
                                      │
                         Compare · Hash · Deduplicate
                                      │
                                      ▼
                              SIGNAL EVENTS
                                      │
                    Exact evidence from public sources
                                      │
                                      ▼
                    CAPABILITY-GAP CLASSIFICATION
                                      │
    Content · Production · Workflow · Platform · Infrastructure · Skills
                                      │
                                      ▼
                       COMPANY-LEVEL AGGREGATION
                                      │
                   Related roles · Momentum · Departments
                                      │
                                      ▼
                       COMMERCIAL QUALIFICATION
                                      │
       Relevance · Actionability · Long-term potential · Strategic value
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                     Watchlist                Research queue
                                                     │
                                           Company research
                                                     │
                                           Opportunity research
                                                     │
                                                     ▼
                                       FTL SOLUTION HYPOTHESIS
                                                     │
                           Create · Build · Deploy · Enable
                                                     │
                   Done-for-you · System · Local AI · Capability transfer
                                                     │
                                                     ▼
                                          HUMAN QUALIFICATION
                                                     │
                                                     ▼
                                      TAILORED OUTREACH DRAFT
                                                     │
                                                     ▼
                                           HUMAN APPROVAL
                                                     │
                                                     ▼
                                      INTERACTION AND OUTCOME DATA
                                                     │
                                                     ▼
                                          LEARNING FEEDBACK LOOP
```

---

# 30. Final Recommendation

FTL should build the platform as a company-owned commercial-intelligence and opportunity-design system.

The system should not only ask:

> Does this company need an AI-generated image, video, webpage, or learning nugget?

It should ask:

> What capability is this organization trying to establish, what visible result could create immediate value, what reusable system would make that result scalable, what infrastructure would make it secure and reliable, and how could FTL enable the internal team to operate and expand it over time?

That question aligns the pipeline with FTL’s long-term identity:

> **A creative technology studio where cinematic vision meets AI engineering—creating the result, building the system behind it, deploying the environment, and removing the barriers between imagination and reality.**
