from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Validate runtime configuration without printing secret values."

    def handle(self, *_args: object, **_options: object) -> None:
        errors = settings.RUNTIME_SETTINGS.safe_validation_errors(
            deploy=settings.RUNTIME_SETTINGS.environment == "production"
        )
        if errors:
            raise CommandError(" ".join(errors))
        self.stdout.write(self.style.SUCCESS("Runtime configuration is valid."))
