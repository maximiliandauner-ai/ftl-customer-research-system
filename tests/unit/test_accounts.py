import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.db.models.deletion import ProtectedError
from django_celery_beat.models import PeriodicTask

from apps.accounts.models import TeamRole, TeamRoleName
from apps.accounts.policy import ROLE_PERMISSION_KEYS
from apps.accounts.services import assign_team_role
from apps.discovery.models import SearchDefinition
from apps.operations.models import AuditEvent, PipelineRun, PipelineStatus, PipelineTrigger
from apps.providers.models import ModelPolicy


@pytest.mark.django_db
def test_bootstrap_is_idempotent_and_seeds_roles_and_schedules(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_command("bootstrap_ftl_platform")
    call_command("bootstrap_ftl_platform")

    assert set(Group.objects.values_list("name", flat=True)) >= set(TeamRoleName.values)
    for role in TeamRoleName:
        group = Group.objects.get(name=role.value)
        assert set(group.permissions.values_list("content_type__app_label", "codename")) == set(
            ROLE_PERMISSION_KEYS[role]
        )
    assert "5 roles (0 new), 3 schedules, 0 new watches" in capsys.readouterr().out
    assert PeriodicTask.objects.filter(enabled=True).count() == 3
    assert set(
        SearchDefinition.objects.filter(active=True).values_list("definition_key", flat=True)
    ) == {
        "ftl-capability-demand",
        "ftl-creative-learning-demand",
        "ftl-learning-enablement-demand",
    }
    assert set(ModelPolicy.objects.filter(active=True).values_list("policy_key", flat=True)) == {
        "discovery.standard_web",
        "research.standard_web",
        "research.standard_extract",
    }


@pytest.mark.django_db
def test_role_assignment_is_mutually_exclusive_group_synced_and_audited() -> None:
    call_command("bootstrap_ftl_platform")
    user = User.objects.create_user(username="operator")

    first = assign_team_role(
        user=user,
        role=TeamRoleName.VIEWER,
        actor=None,
        reason="initial_access",
    )
    second = assign_team_role(
        user=user,
        role=TeamRoleName.FOUNDER,
        actor=user,
        reason="responsibility_change",
    )

    assert first.pk == second.pk
    assert TeamRole.objects.get(user=user).role == TeamRoleName.FOUNDER
    assert list(user.groups.values_list("name", flat=True)) == [TeamRoleName.FOUNDER]
    assert AuditEvent.objects.filter(action="accounts.team_role_assigned").count() == 2
    assert AuditEvent.objects.first().actor_type == "user"


@pytest.mark.django_db
def test_deactivation_retains_role_and_historical_authorship() -> None:
    call_command("bootstrap_ftl_platform")
    user = User.objects.create_user(username="historian")
    assign_team_role(
        user=user,
        role=TeamRoleName.REVIEWER,
        actor=None,
        reason="initial_access",
    )
    run = PipelineRun.objects.create(
        pipeline_name="history",
        stage="complete",
        status=PipelineStatus.COMPLETE,
        trigger=PipelineTrigger.MANUAL,
        requested_by=user,
        idempotency_key="history:retained",
    )

    user.is_active = False
    user.save(update_fields=("is_active",))
    run.refresh_from_db()

    assert run.requested_by == user
    assert TeamRole.objects.get(user=user).role == TeamRoleName.REVIEWER
    with pytest.raises(ProtectedError):
        user.delete()


@pytest.mark.django_db
def test_assign_team_role_command_rejects_unknown_user() -> None:
    call_command("bootstrap_ftl_platform")

    with pytest.raises(Exception, match="Unknown user"):
        call_command("assign_team_role", "missing", "viewer", reason="test")


@pytest.mark.django_db
def test_permission_catalog_exists_after_migration() -> None:
    expected = set().union(*ROLE_PERMISSION_KEYS.values())
    actual = set(Permission.objects.values_list("content_type__app_label", "codename"))

    assert expected <= actual
