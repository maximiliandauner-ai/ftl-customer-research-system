import uuid

from django.core.management.base import BaseCommand, CommandParser

from apps.operations.contracts import CreateCheckpointCommandV1
from apps.operations.services import create_checkpoint_command


class Command(BaseCommand):
    help = "Create a system-owned checkpoint through the durable transactional outbox."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--idempotency-key")

    def handle(self, *_args: object, **options: object) -> None:
        supplied_key = options.get("idempotency_key")
        key = (
            supplied_key
            if isinstance(supplied_key, str) and supplied_key
            else f"operations.checkpoint:{uuid.uuid4()}"
        )
        result = create_checkpoint_command(
            command=CreateCheckpointCommandV1(idempotency_key=key),
            actor=None,
        )
        outcome = "created" if result.created else "reused"
        self.stdout.write(
            self.style.SUCCESS(
                f"Checkpoint {outcome}: run={result.pipeline_run.pk} outbox={result.outbox.pk}."
            )
        )
