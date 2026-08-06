from django.contrib import admin

from apps.research.models import (
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchClaimSignal,
    ResearchClaimSource,
    ResearchDossier,
    ResearchReportArtifact,
    ResearchRun,
    ResearchSource,
)

admin.site.register(ResearchRun)
admin.site.register(ResearchReportArtifact)
admin.site.register(ResearchSource)
admin.site.register(ResearchClaim)
admin.site.register(ResearchClaimSource)
admin.site.register(ResearchClaimSignal)
admin.site.register(ResearchClaimEvidence)
admin.site.register(ResearchDossier)
