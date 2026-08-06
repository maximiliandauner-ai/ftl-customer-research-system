from django.contrib import admin

from apps.opportunities.models import (
    CompanyAssessment,
    CompanyFeature,
    CompanyPattern,
    Opportunity,
    OpportunitySignal,
    QualificationOverride,
)

admin.site.register(CompanyAssessment)
admin.site.register(CompanyFeature)
admin.site.register(CompanyPattern)
admin.site.register(Opportunity)
admin.site.register(OpportunitySignal)
admin.site.register(QualificationOverride)
