from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Fail unless every migration in the built image is already applied."

    def handle(self, *_args: object, **_options: object) -> None:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            labels = ", ".join(
                f"{migration.app_label}.{migration.name}" for migration, _ in plan[:10]
            )
            raise CommandError(f"Pending migrations: {labels}")
        self.stdout.write(self.style.SUCCESS("All migrations are applied."))
