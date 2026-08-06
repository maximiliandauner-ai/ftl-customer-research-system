from django.contrib import admin

from apps.solutions.models import (
    AssetMatch,
    AssetSelection,
    OpportunitySolutionState,
    SolutionPhase,
    SolutionVersion,
)

admin.site.register(SolutionVersion)
admin.site.register(OpportunitySolutionState)
admin.site.register(SolutionPhase)
admin.site.register(AssetMatch)
admin.site.register(AssetSelection)
