import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from pydantic import ValidationError

from apps.operations.commands import (
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
)
from apps.operations.models import AuditEvent, PipelineStatus, TaskOutbox
from apps.operations.outbox import build_envelope
from apps.opportunities.models import (
    CompanyAssessment,
    CompanyFeature,
    Opportunity,
    OpportunitySignal,
    QualificationStatus,
)
from apps.opportunities.services import (
    execute_company_aggregation,
    override_qualification,
)
from apps.signals.assessment_contracts import CapabilityAssessmentV2
from apps.signals.classification import (
    execute_signal_classification,
    override_assessment_mode,
)
from apps.signals.models import (
    AssessmentOverride,
    CapabilityGapRecord,
    OpportunityMode,
    SignalAssessment,
    SignalAssessmentEvidence,
)
from apps.signals.services import execute_signal_detection, retract_signal
from tests.unit.test_job_services import ASHBY_FIXTURE, poll_ashby


def _ashby_body(description: str) -> bytes:
    payload = json.loads(ASHBY_FIXTURE.read_text())
    payload["jobs"][0]["descriptionPlain"] = description
    payload["jobs"][0]["department"] = "Operations"
    return json.dumps(payload).encode()


def _execute_pipeline() -> tuple[SignalAssessment, CompanyAssessment, Opportunity]:
    detection = TaskOutbox.objects.get(command_type="signals.detect")
    assert execute_signal_detection(build_envelope(detection))
    classification = TaskOutbox.objects.get(command_type=SIGNALS_CLASSIFY_COMMAND_TYPE)
    assert execute_signal_classification(build_envelope(classification))
    aggregation = TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE)
    assert execute_company_aggregation(build_envelope(aggregation))
    return (
        SignalAssessment.objects.get(),
        CompanyAssessment.objects.get(),
        Opportunity.objects.get(),
    )


@pytest.mark.django_db
def test_signal_classification_and_company_aggregation_are_durable_and_replay_safe(
    tmp_path,
) -> None:
    user = User.objects.create_user(username="aggregation-hoffmann")
    poll_ashby(
        user,
        "aggregation:created",
        _ashby_body(
            "Design workflow automation and a governed knowledge base. "
            "Own data integration across operating systems."
        ),
        tmp_path,
    )

    assessment, company_assessment, opportunity = _execute_pipeline()

    assert assessment.status == "completed"
    assert assessment.opportunity_mode == OpportunityMode.HYBRID
    assert assessment.capability_relevance is not None
    assert Decimal("0") < assessment.score_coverage < Decimal("1")
    assert "portfolio_proof_availability" in assessment.missing_components
    assert set(assessment.capability_clusters.values_list("cluster_key", flat=True)) == {
        "workflow_design",
        "knowledge_architecture",
        "integration_architecture",
    }
    assert CapabilityGapRecord.objects.filter(assessment=assessment).count() == 3
    assert SignalAssessmentEvidence.objects.filter(assessment=assessment).exists()
    assert company_assessment.priority_score == opportunity.priority_score
    assert company_assessment.overall_coverage == opportunity.score_coverage
    assert CompanyFeature.objects.filter(company_assessment=company_assessment).count() >= 20
    assert "isolated_experiment" in company_assessment.pattern_keys
    assert opportunity.qualification_status == QualificationStatus.RESEARCH_ELIGIBLE
    assert OpportunitySignal.objects.filter(opportunity=opportunity).count() == 1
    aggregation = TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE)
    assert execute_company_aggregation(build_envelope(aggregation)) is False
    assert CompanyAssessment.objects.count() == 1
    assert AuditEvent.objects.filter(action="signals.classification_completed").count() == 1
    assert AuditEvent.objects.filter(action="companies.aggregation_completed").count() == 1
    aggregation.pipeline_run.refresh_from_db()
    assert aggregation.pipeline_run.status == PipelineStatus.COMPLETE


@pytest.mark.django_db
def test_human_overrides_are_separate_and_survive_automatic_rescoring(tmp_path) -> None:
    actor = User.objects.create_user(username="opportunity-reviewer")
    poll_ashby(
        actor,
        "override:created",
        _ashby_body("Build workflow automation and data integration for operations."),
        tmp_path,
    )
    assessment, _company_assessment, opportunity = _execute_pipeline()

    mode_override = override_assessment_mode(
        assessment_id=assessment.pk,
        actor=actor,
        opportunity_mode=OpportunityMode.EXTERNAL_SERVICE,
        reason="Confirmed external delivery route in review.",
        request_id=None,
    )
    assert assessment.opportunity_mode == OpportunityMode.HYBRID
    assert AssessmentOverride.objects.get(pk=mode_override.pk).opportunity_mode == (
        OpportunityMode.EXTERNAL_SERVICE
    )
    override_qualification(
        opportunity_id=opportunity.pk,
        actor=actor,
        selected_status=QualificationStatus.QUALIFIED,
        reason="Founder reviewed the evidence and approved qualification.",
        request_id=None,
    )
    override_run = TaskOutbox.objects.get(
        pipeline_run__context__cause_key=f"assessment-override:{mode_override.pk}"
    )
    assert execute_company_aggregation(build_envelope(override_run))
    opportunity.refresh_from_db()
    assert opportunity.opportunity_mode == OpportunityMode.EXTERNAL_SERVICE
    assert opportunity.qualification_status == QualificationStatus.QUALIFIED
    assert CompanyAssessment.objects.filter(status="superseded").exists()


@pytest.mark.django_db
def test_false_positive_retraction_removes_the_active_opportunity_without_deleting_history(
    tmp_path,
) -> None:
    actor = User.objects.create_user(username="signal-retraction-reviewer")
    poll_ashby(
        actor,
        "retraction:created",
        _ashby_body("Build workflow automation and data integration for operations."),
        tmp_path,
    )
    assessment, _company_assessment, opportunity = _execute_pipeline()

    retract_signal(
        signal_id=assessment.signal_id,
        actor=actor,
        reason="Reviewed source evidence shows a false positive.",
        request_id=None,
    )
    retraction_run = TaskOutbox.objects.get(
        pipeline_run__context__cause_key__startswith="signal-retraction:"
    )
    assert execute_company_aggregation(build_envelope(retraction_run))
    opportunity.refresh_from_db()
    assert not opportunity.active
    assert Opportunity.objects.filter(pk=opportunity.pk).exists()
    assert CompanyAssessment.objects.filter(selected_signal_ids=[]).exists()


def test_capability_assessment_contract_rejects_extra_or_overlapping_mode_fields() -> None:
    valid = {
        "schema_version": "2.1",
        "prompt_version": "2.1.0",
        "capability_clusters": (),
        "capability_gaps": (),
        "opportunity_mode": "unknown",
        "mode_confidence": 0.2,
        "mode_evidence_ids": (),
        "mode_rationale": "The supplied evidence does not support a route.",
        "recommended_ftl_layers": (),
        "entry_offer_candidates": (),
        "component_judgments": {
            "task_overlap": {"score": 20, "confidence": 0.3},
            "reusable_system_potential": {"score": 20, "confidence": 0.3},
            "enablement_potential": {"score": 20, "confidence": 0.3},
            "infrastructure_relevance": {"value": "unknown", "confidence": 0.2},
            "vendor_receptivity": {"value": "unknown", "confidence": 0.0},
        },
        "unknowns": (),
        "review_flags": (),
    }
    assert CapabilityAssessmentV2.model_validate(valid).opportunity_mode == "unknown"
    with pytest.raises(ValidationError):
        CapabilityAssessmentV2.model_validate({**valid, "hybrid_probability": 0.8})
