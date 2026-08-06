from django.contrib import admin

from apps.knowledge.models import (
    ApprovedClaim,
    Asset,
    KnowledgeActivationEvent,
    KnowledgeRegistryState,
    KnowledgeRelease,
    OfferModule,
    ProhibitedClaim,
)

admin.site.register(KnowledgeRelease)
admin.site.register(KnowledgeRegistryState)
admin.site.register(OfferModule)
admin.site.register(ApprovedClaim)
admin.site.register(ProhibitedClaim)
admin.site.register(Asset)
admin.site.register(KnowledgeActivationEvent)
