import uuid

import pytest
from pydantic import ValidationError

from apps.operations.contracts import (
    CheckpointPayloadV1,
    CreateCheckpointCommandV1,
    TaskEnvelopeV2,
)


def test_task_envelope_accepts_ids_and_scalars_only() -> None:
    identifier = uuid.uuid4()
    envelope = TaskEnvelopeV2(
        outbox_id=identifier,
        pipeline_run_id=identifier,
        command_type="operations.complete_checkpoint",
        object_id=identifier,
        idempotency_key="checkpoint:12345678",
        requested_by="system",
    )

    assert envelope.schema_version == "2.1"
    assert envelope.force is False


@pytest.mark.parametrize("requested_by", ["operator", "", "provider:abc"])
def test_task_envelope_rejects_untrusted_actor_references(requested_by: str) -> None:
    identifier = uuid.uuid4()
    with pytest.raises(ValidationError):
        TaskEnvelopeV2(
            outbox_id=identifier,
            pipeline_run_id=identifier,
            command_type="operations.complete_checkpoint",
            object_id=identifier,
            idempotency_key="checkpoint:12345678",
            requested_by=requested_by,
        )


def test_contracts_reject_extra_or_malformed_fields() -> None:
    with pytest.raises(ValidationError):
        CreateCheckpointCommandV1(
            idempotency_key="spaces are unsafe",
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        CheckpointPayloadV1.model_validate(
            {"pipeline_run_id": str(uuid.uuid4()), "raw_source_body": "never broker this"}
        )
