from django.contrib import admin

from apps.contacts.models import (
    BuyerRoleHypothesis,
    BuyerRoleResult,
    ContactEvidence,
    ContactObservation,
    ContactPerson,
    ContactResearchRun,
    ContactRoute,
    ContactSelection,
    ContactSourceArtifact,
    ContactSourceTarget,
    SuppressionEntry,
)

admin.site.register(ContactResearchRun)
admin.site.register(BuyerRoleResult)
admin.site.register(BuyerRoleHypothesis)
admin.site.register(ContactSourceTarget)
admin.site.register(ContactSourceArtifact)
admin.site.register(ContactEvidence)
admin.site.register(ContactPerson)
admin.site.register(ContactObservation)
admin.site.register(ContactRoute)
admin.site.register(SuppressionEntry)
admin.site.register(ContactSelection)
