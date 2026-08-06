import uuid
from typing import cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.sources.contracts import SubmitPublicSourceV1
from apps.sources.services import submit_public_source


class Command(BaseCommand):
    help = "Submit one confirmed public source through the audited ingestion workflow."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("url")
        parser.add_argument("--username", required=True)
        parser.add_argument("--company-name")
        parser.add_argument("--company-domain")
        parser.add_argument("--idempotency-key")
        parser.add_argument("--confirm-public", action="store_true")

    def handle(self, *_args: object, **options: object) -> None:
        if not options["confirm_public"]:
            raise CommandError("--confirm-public is required for an external fetch request.")
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"], is_active=True)
        except user_model.DoesNotExist as exc:
            raise CommandError("The requested active operator does not exist.") from exc
        if not user.has_perm("sources.submit_public_source"):
            raise CommandError("The operator is not permitted to submit public sources.")
        requested_url = cast(str, options["url"])
        company_name = cast(str | None, options.get("company_name"))
        company_domain = cast(str | None, options.get("company_domain"))
        key = cast(str | None, options.get("idempotency_key")) or f"sources.manual:{uuid.uuid4()}"
        result = submit_public_source(
            command=SubmitPublicSourceV1(
                requested_url=requested_url,
                company_name=company_name,
                company_domain=company_domain,
                idempotency_key=key,
                public_source_confirmed=True,
            ),
            actor=user,
            policy=settings.RUNTIME_SETTINGS.fetch,
        )
        outcome = "queued" if result.accepted else "rejected"
        self.stdout.write(
            self.style.SUCCESS(
                f"Public source {outcome}: candidate={result.candidate.pk} "
                f"endpoint={result.endpoint.pk if result.endpoint else '-'} "
                f"run={result.pipeline_run.pk if result.pipeline_run else '-'}"
            )
        )
