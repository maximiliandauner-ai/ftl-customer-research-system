from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.companies.services import schedule_due_company_enrichments


class Command(BaseCommand):
    help = "Queue bounded source-backed profile enrichment for existing companies."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args: object, **options: Any) -> None:
        seen, created = schedule_due_company_enrichments(limit=int(options["limit"]))
        self.stdout.write(
            self.style.SUCCESS(f"Eligible companies: {seen}; newly queued: {created}")
        )
