from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.jobs.services import create_reparse_command
from apps.sources.models import SourceSnapshot


class Command(BaseCommand):
    help = "Queue a durable deterministic reparse of an immutable source snapshot."

    def add_arguments(self, parser: object) -> None:
        parser.add_argument("source_snapshot_id", type=UUID)  # type: ignore[attr-defined]

    def handle(self, *_args: object, **options: object) -> None:
        snapshot_id = UUID(str(options["source_snapshot_id"]))
        try:
            snapshot = SourceSnapshot.objects.get(pk=snapshot_id)
        except SourceSnapshot.DoesNotExist as exc:
            raise CommandError("Source snapshot does not exist.") from exc
        run, outbox, _created = create_reparse_command(snapshot)
        self.stdout.write(
            self.style.SUCCESS(f"Queued parse run {run.pk} via outbox command {outbox.pk}.")
        )
