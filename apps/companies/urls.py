from django.urls import path

from apps.companies import views

app_name = "companies"

urlpatterns = [
    path("", views.company_list, name="list"),
    path("<uuid:company_id>/", views.company_detail, name="detail"),
]
