from django.conf import settings

from domain.queues import QUEUE_POLICY


def test_queue_policy_matches_celery_configuration() -> None:
    configured = {queue.name for queue in settings.CELERY_TASK_QUEUES}

    assert QUEUE_POLICY.schema_version == "1.1"
    assert configured == set(QUEUE_POLICY.names)
    assert settings.CELERY_RESULT_BACKEND is None
    assert settings.CELERY_TASK_IGNORE_RESULT is True
    assert settings.CELERY_ACCEPT_CONTENT == ["json"]
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1
    for queue in settings.CELERY_TASK_QUEUES:
        assert queue.exchange.name == f"ftl.v1.{queue.name}"
        assert queue.exchange.type == "direct"
        assert queue.routing_key == queue.name
