from django.urls import path

from apps.solutions import views

app_name = "solutions"

urlpatterns = [
    path("", views.solution_list, name="list"),
    path("<uuid:solution_id>/", views.solution_detail, name="detail"),
    path("opportunities/<uuid:opportunity_id>/request/", views.request_solution, name="request"),
    path("<uuid:solution_id>/edit/", views.edit_solution, name="edit"),
    path("<uuid:solution_id>/approve/", views.approve_solution_view, name="approve"),
]
