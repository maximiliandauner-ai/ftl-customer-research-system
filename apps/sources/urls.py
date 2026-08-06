from django.urls import path

from apps.sources import views

app_name = "sources"

urlpatterns = [
    path("", views.source_index, name="index"),
    path("submit/", views.submit_source, name="submit"),
    path("candidates/<uuid:candidate_id>/", views.candidate_detail, name="candidate-detail"),
    path("endpoints/<uuid:endpoint_id>/", views.endpoint_detail, name="endpoint-detail"),
    path("attempts/<uuid:attempt_id>/", views.attempt_detail, name="attempt-detail"),
    path("artifacts/<uuid:artifact_id>/", views.artifact_detail, name="artifact-detail"),
]
