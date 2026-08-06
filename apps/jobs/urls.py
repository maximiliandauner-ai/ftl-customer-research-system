from django.urls import path

from apps.jobs import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="list"),
    path("<uuid:posting_id>/", views.job_detail, name="detail"),
]
