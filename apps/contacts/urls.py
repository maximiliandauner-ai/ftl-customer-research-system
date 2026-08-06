from django.urls import path

from apps.contacts import views

app_name = "contacts"

urlpatterns = [
    path("", views.contact_list, name="list"),
    path("<uuid:contact_run_id>/", views.contact_detail, name="detail"),
    path("request/<uuid:opportunity_id>/", views.request_contacts, name="request"),
    path("human-route/<uuid:contact_run_id>/", views.add_human_route, name="human-route"),
    path("route/<uuid:route_id>/review/", views.review_route, name="review-route"),
    path("route/<uuid:route_id>/select/", views.select_route, name="select-route"),
    path("route/<uuid:route_id>/suppress/", views.suppress_route, name="suppress-route"),
]
