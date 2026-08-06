from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.discovery.models import SearchDefinition
from apps.discovery.services import create_discovery_run


class Command(BaseCommand):
    help = "Queue one manual discovery run through the transactional outbox."

    def add_arguments(self, parser: object) -> None:
        parser.add_argument(  # type: ignore[attr-defined]
            "--definition-key",
            default="ftl-capability-demand",
            help="Active SearchDefinition key to run.",
        )

    def handle(self, *_args: object, **options: object) -> None:
        definition_key = str(options["definition_key"])
        definition = SearchDefinition.objects.filter(
            definition_key=definition_key,
            active=True,
        ).first()
        if definition is None:
            raise CommandError(f"No active search definition named {definition_key!r}.")
        window_end = timezone.now()
        result = create_discovery_run(
            definition,
            logical_window_start=window_end - timedelta(days=definition.lookback_days),
            logical_window_end=window_end,
            reason="manual",
            actor=None,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Discovery run {result.run.pk} is {result.run.status}; outbox {result.outbox.pk}."
            )
        )
