from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.opportunities.services import schedule_all_current_companies


class Command(BaseCommand):
    help = "Queue bounded company aggregation for current completed signal assessments."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: object, **options: Any) -> None:
        limit = max(1, min(int(options["limit"]), 5_000))
        created = schedule_all_current_companies(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"New company aggregations queued: {created}"))
