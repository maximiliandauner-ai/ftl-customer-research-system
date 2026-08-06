from django.urls import path

from apps.operations import views

app_name = "operations"

urlpatterns = [
    path("", views.operations_index, name="index"),
    path("runs/", views.run_list, name="run-list"),
    path("runs/<uuid:run_id>/", views.run_detail, name="run-detail"),
    path("outbox/", views.outbox_list, name="outbox-list"),
    path("outbox/<uuid:outbox_id>/", views.outbox_detail, name="outbox-detail"),
    path("outbox/<uuid:outbox_id>/retry/", views.retry_outbox, name="outbox-retry"),
    path("audit/", views.audit_list, name="audit-list"),
    path("commands/checkpoint/", views.create_checkpoint, name="checkpoint-create"),
]
