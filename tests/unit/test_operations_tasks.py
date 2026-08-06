from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.operations.contracts import CreateCheckpointCommandV1
from apps.operations.models import PipelineStepRun
from apps.operations.outbox import CeleryPublisher, build_envelope
from apps.operations.services import create_checkpoint_command
from apps.operations.tasks import (
    complete_checkpoint_task,
    dispatch_outbox_task,
    recover_stale_outbox_task,
)


@pytest.mark.django_db
def test_celery_checkpoint_task_validates_envelope_and_executes_once() -> None:
    user = User.objects.create_user(username="celery-consumer")
    created = create_checkpoint_command(
        command=CreateCheckpointCommandV1(idempotency_key="operations.checkpoint:celery-task"),
        actor=user,
    )
    envelope = build_envelope(created.outbox)

    complete_checkpoint_task.run(envelope.model_dump(mode="json"))
    complete_checkpoint_task.run(envelope.model_dump(mode="json"))

    assert PipelineStepRun.objects.filter(pipeline_run=created.pipeline_run).count() == 1


def test_maintenance_tasks_delegate_to_bounded_services() -> None:
    with patch("apps.operations.tasks.dispatch_outbox_batch") as dispatch:
        dispatch_outbox_task.run()
    with patch("apps.operations.tasks.recover_stale_claims") as recover:
        recover_stale_outbox_task.run()

    dispatch.assert_called_once_with()
    recover.assert_called_once_with()


def test_celery_publisher_routes_small_json_envelope_to_maintenance() -> None:
    identifier = uuid4()
    from apps.operations.contracts import TaskEnvelopeV2

    envelope = TaskEnvelopeV2(
        outbox_id=identifier,
        pipeline_run_id=identifier,
        command_type="operations.complete_checkpoint",
        object_id=identifier,
        idempotency_key="operations.checkpoint:publisher:dispatch",
        requested_by="system",
        request_id=uuid4(),
    )
    with patch(
        "apps.operations.outbox.celery_app.send_task",
        return_value=SimpleNamespace(id="message-42"),
    ) as send_task:
        published = CeleryPublisher().publish(envelope)

    assert published.message_id == "message-42"
    assert send_task.call_args.kwargs["queue"] == "maintenance"
    assert "exchange" not in send_task.call_args.kwargs
    assert "routing_key" not in send_task.call_args.kwargs
    assert send_task.call_args.args == ("operations.complete_checkpoint",)
    assert list(send_task.call_args.kwargs["args"][0]) == list(envelope.model_dump(mode="json"))


@pytest.mark.django_db
def test_checkpoint_management_command_is_idempotent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    key = "operations.checkpoint:management"
    call_command("create_operations_checkpoint", idempotency_key=key)
    call_command("create_operations_checkpoint", idempotency_key=key)

    output = capsys.readouterr().out
    assert "Checkpoint created" in output
    assert "Checkpoint reused" in output


def test_dispatch_management_command_reports_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch(
        "apps.operations.management.commands.dispatch_outbox.dispatch_outbox_batch",
        return_value=3,
    ):
        call_command("dispatch_outbox", limit=7)

    assert "Published 3 outbox command(s)." in capsys.readouterr().out
