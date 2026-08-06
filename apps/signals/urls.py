from django.urls import path

from apps.signals import views

app_name = "signals"

urlpatterns = [
    path("", views.signal_list, name="list"),
    path("<uuid:signal_id>/", views.signal_detail, name="detail"),
    path("<uuid:signal_id>/retract/", views.retract, name="retract"),
    path(
        "<uuid:signal_id>/assessment/override/",
        views.assessment_override,
        name="assessment-override",
    ),
]
