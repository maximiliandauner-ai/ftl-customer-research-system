from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role


class Command(BaseCommand):
    help = "Assign one canonical FTL role to an existing user."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username")
        parser.add_argument("role", choices=TeamRoleName.values)
        parser.add_argument("--reason", required=True)

    def handle(self, *_args: object, **options: object) -> None:
        username = str(options["username"])
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=username)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Unknown user: {username}.") from exc
        role = assign_team_role(
            user=user,
            role=TeamRoleName(str(options["role"])),
            actor=None,
            reason=str(options["reason"]),
        )
        self.stdout.write(self.style.SUCCESS(f"Assigned {role.role} to {username}."))
