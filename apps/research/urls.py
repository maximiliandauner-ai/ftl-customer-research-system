from django.urls import path

from apps.research import views

app_name = "research"

urlpatterns = [
    path("", views.research_list, name="list"),
    path("<uuid:research_run_id>/", views.research_detail, name="detail"),
    path(
        "opportunities/<uuid:opportunity_id>/request/",
        views.request_research,
        name="request",
    ),
]
