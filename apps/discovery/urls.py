from django.urls import path

from apps.discovery import views

app_name = "discovery"

urlpatterns = [
    path("", views.discovery_index, name="index"),
    path("definitions/", views.discovery_index, name="definitions"),
    path("candidates/", views.discovery_candidate_list, name="candidate-list"),
    path("definitions/<uuid:definition_id>/run/", views.run_definition, name="run-definition"),
    path("runs/<uuid:run_id>/", views.discovery_run_detail, name="run-detail"),
]
