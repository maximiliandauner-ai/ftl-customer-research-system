from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.knowledge.services import KnowledgeValidationError, sync_knowledge_release


class Command(BaseCommand):
    help = "Validate and append an immutable FTL knowledge release."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--commit", required=True)
        parser.add_argument("--source-root", default=str(settings.BASE_DIR / "knowledge_base"))
        parser.add_argument("--username")
        parser.add_argument("--validate", action="store_true", required=True)

    def handle(self, *_args: object, **options: Any) -> None:
        actor = None
        if options.get("username"):
            try:
                actor = User.objects.get(username=options["username"], is_active=True)
            except User.DoesNotExist as exc:
                raise CommandError("The requested active sync user does not exist.") from exc
            if not actor.has_perm("knowledge.sync_knowledge"):
                raise CommandError("The requested user may not sync FTL knowledge releases.")
        try:
            result = sync_knowledge_release(
                source_root=Path(options["source_root"]),
                source_commit=options["commit"],
                actor=actor,
            )
        except KnowledgeValidationError as exc:
            raise CommandError(str(exc)) from exc
        outcome = "created" if result.created else "already present"
        self.stdout.write(
            self.style.SUCCESS(
                f"Knowledge release v{result.release.version} {outcome}: {result.release.pk}"
            )
        )
