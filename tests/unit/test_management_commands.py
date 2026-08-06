from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.core.checks import production_configuration_check, runtime_configuration_check


@pytest.mark.django_db
def test_migrations_applied_check_succeeds_for_current_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_command("migrations_applied_check")

    assert "All migrations are applied." in capsys.readouterr().out


def test_migrations_applied_check_names_pending_migration() -> None:
    migration = SimpleNamespace(app_label="operations", name="0001_initial")
    executor = Mock()
    executor.loader.graph.leaf_nodes.return_value = []
    executor.migration_plan.return_value = [(migration, False)]

    with (
        patch(
            "apps.core.management.commands.migrations_applied_check.MigrationExecutor",
            return_value=executor,
        ),
        pytest.raises(CommandError, match=r"operations\.0001_initial"),
    ):
        call_command("migrations_applied_check")


def test_validate_runtime_reports_success(capsys: pytest.CaptureFixture[str]) -> None:
    call_command("validate_runtime")

    assert "Runtime configuration is valid." in capsys.readouterr().out


def test_validate_runtime_fails_without_exposing_values() -> None:
    runtime = Mock()
    runtime.environment = "production"
    runtime.safe_validation_errors.return_value = ("Unsafe production configuration.",)

    with (
        override_settings(RUNTIME_SETTINGS=runtime),
        pytest.raises(CommandError, match="Unsafe production configuration"),
    ):
        call_command("validate_runtime")


def test_system_checks_convert_safe_validation_errors() -> None:
    runtime = Mock()
    runtime.safe_validation_errors.return_value = ("Blocked unsafe setting.",)

    with override_settings(RUNTIME_SETTINGS=runtime):
        runtime_errors = runtime_configuration_check()
        production_errors = production_configuration_check()

    assert [error.msg for error in runtime_errors] == ["Blocked unsafe setting."]
    assert [error.msg for error in production_errors] == ["Blocked unsafe setting."]
    runtime.safe_validation_errors.assert_any_call(deploy=False)
    runtime.safe_validation_errors.assert_any_call(deploy=True)
