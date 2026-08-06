from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.knowledge.models import KnowledgeRelease
from apps.knowledge.services import KnowledgeValidationError, activate_knowledge_release


class Command(BaseCommand):
    help = "Activate one validated FTL knowledge release with an audited human reason."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("release_id", type=UUID)
        parser.add_argument("--username", required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *_args: object, **options: Any) -> None:
        try:
            actor = User.objects.get(username=options["username"], is_active=True)
            if not actor.has_perm("knowledge.activate_knowledge"):
                raise CommandError("The requested user may not activate FTL knowledge releases.")
            event = activate_knowledge_release(
                release_id=options["release_id"],
                actor=actor,
                reason=options["reason"],
            )
        except (User.DoesNotExist, KnowledgeRelease.DoesNotExist) as exc:
            raise CommandError("The requested active user or release does not exist.") from exc
        except KnowledgeValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Knowledge release v{event.activated_release.version} is active.")
        )
