from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.jobs.models import PostingChangeEvent, PostingChangeType
from apps.operations.models import PipelineTrigger
from apps.signals.services import schedule_signal_detection


class Command(BaseCommand):
    help = "Queue bounded deterministic signal detection for existing eligible job changes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: object, **options: Any) -> None:
        limit = max(1, min(int(options["limit"]), 5_000))
        events = (
            PostingChangeEvent.objects.filter(
                change_type__in=(
                    PostingChangeType.CREATED,
                    PostingChangeType.MATERIAL,
                    PostingChangeType.CLOSED,
                    PostingChangeType.REOPENED,
                ),
                new_snapshot__isnull=False,
            )
            .select_related("parse_run")
            .order_by("created_at")[:limit]
        )
        created = 0
        seen = 0
        for event in events:
            result = schedule_signal_detection(event, trigger=PipelineTrigger.BACKFILL)
            seen += 1
            if result is not None and result.created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Eligible events: {seen}; newly queued: {created}"))
