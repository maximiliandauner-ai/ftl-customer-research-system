from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.signals.classification import schedule_signal_classification
from apps.signals.models import SignalEvent, SignalStatus


class Command(BaseCommand):
    help = "Queue bounded deterministic classification for active evidence-backed signals."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: object, **options: Any) -> None:
        limit = max(1, min(int(options["limit"]), 5_000))
        signals = (
            SignalEvent.objects.filter(status=SignalStatus.ACTIVE)
            .select_related("detection_attempt__pipeline_run")
            .order_by("created_at")[:limit]
        )
        created = 0
        seen = 0
        for signal in signals:
            result = schedule_signal_classification(signal)
            seen += 1
            if result is not None and result.created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Active signals: {seen}; newly queued: {created}"))
