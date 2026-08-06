from django.contrib import admin

from apps.signals.models import (
    AssessmentOverride,
    CapabilityClusterRecord,
    CapabilityGapRecord,
    SignalAssessment,
    SignalAssessmentEvidence,
    SignalDetectionAttempt,
    SignalEvent,
    SignalEvidence,
    SignalOntology,
)

admin.site.register(SignalOntology)
admin.site.register(SignalDetectionAttempt)
admin.site.register(SignalEvent)
admin.site.register(SignalEvidence)
admin.site.register(SignalAssessment)
admin.site.register(SignalAssessmentEvidence)
admin.site.register(CapabilityClusterRecord)
admin.site.register(CapabilityGapRecord)
admin.site.register(AssessmentOverride)
