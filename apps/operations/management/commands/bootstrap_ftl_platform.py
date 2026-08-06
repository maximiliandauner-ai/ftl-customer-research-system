from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from apps.accounts.models import TeamRoleName
from apps.accounts.policy import ROLE_PERMISSION_CODENAMES


class Command(BaseCommand):
    help = "Idempotently seed FTL roles, permissions, and safe platform schedules."

    @transaction.atomic
    def handle(self, *_args: object, **_options: object) -> None:
        group_count = 0
        for role in TeamRoleName:
            group, created = Group.objects.get_or_create(name=role.value)
            codenames = ROLE_PERMISSION_CODENAMES[role]
            permissions = Permission.objects.filter(
                content_type__app_label="operations",
                codename__in=codenames,
            )
            found = {permission.codename for permission in permissions}
            missing = set(codenames) - found
            if missing:
                raise CommandError(
                    f"Missing operations permissions after migration: {', '.join(sorted(missing))}."
                )
            group.permissions.set(permissions)
            group_count += int(created)

        dispatch_interval, _created = IntervalSchedule.objects.get_or_create(
            every=10,
            period=IntervalSchedule.SECONDS,
        )
        recovery_interval, _created = IntervalSchedule.objects.get_or_create(
            every=60,
            period=IntervalSchedule.SECONDS,
        )
        PeriodicTask.objects.update_or_create(
            name="FTL outbox dispatch",
            defaults={
                "task": "operations.dispatch_outbox",
                "interval": dispatch_interval,
                "queue": "maintenance",
                "enabled": True,
                "args": "[]",
                "kwargs": "{}",
            },
        )
        PeriodicTask.objects.update_or_create(
            name="FTL stale outbox recovery",
            defaults={
                "task": "operations.recover_stale_outbox",
                "interval": recovery_interval,
                "queue": "maintenance",
                "enabled": True,
                "args": "[]",
                "kwargs": "{}",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"FTL platform policy ready: 5 roles ({group_count} new), 2 schedules."
            )
        )
