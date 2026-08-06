from django.urls import path

from apps.core.views import dependencies, live, ready

urlpatterns = [
    path("live", live, name="health-live"),
    path("ready", ready, name="health-ready"),
    path("dependencies", dependencies, name="health-dependencies"),
]
