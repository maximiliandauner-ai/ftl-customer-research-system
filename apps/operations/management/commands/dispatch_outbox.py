from django.core.management.base import BaseCommand, CommandParser

from apps.operations.outbox import dispatch_outbox_batch


class Command(BaseCommand):
    help = "Claim and publish one bounded batch of durable outbox commands."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *_args: object, **options: object) -> None:
        limit = options.get("limit")
        if not isinstance(limit, int):
            limit = 100
        published = dispatch_outbox_batch(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Published {published} outbox command(s)."))
