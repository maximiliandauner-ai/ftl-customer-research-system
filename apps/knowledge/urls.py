from django.urls import path

from apps.knowledge import views

app_name = "knowledge"

urlpatterns = [
    path("", views.release_list, name="list"),
    path("<uuid:release_id>/", views.release_detail, name="detail"),
    path("<uuid:release_id>/activate/", views.activate_release, name="activate"),
]
