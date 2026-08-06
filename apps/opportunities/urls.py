from django.urls import path

from apps.opportunities import views

app_name = "opportunities"

urlpatterns = [
    path("", views.opportunity_list, name="list"),
    path("<uuid:opportunity_id>/", views.opportunity_detail, name="detail"),
    path(
        "<uuid:opportunity_id>/qualification/",
        views.qualification_override,
        name="qualification-override",
    ),
]
