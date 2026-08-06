from __future__ import annotations

from uuid import UUID

from django.contrib.auth.models import Group
from django.contrib.auth.models import User as DjangoUser
from django.db import transaction

from apps.accounts.models import TeamRole, TeamRoleName
from apps.operations.models import ActorType, AuditEvent


@transaction.atomic
def assign_team_role(
    *,
    user: DjangoUser,
    role: TeamRoleName,
    actor: DjangoUser | None,
    request_id: UUID | None = None,
    reason: str,
) -> TeamRole:
    locked_user = DjangoUser.objects.select_for_update().get(pk=user.pk)
    current = TeamRole.objects.select_for_update().filter(user=locked_user).first()
    before_role = current.role if current else None
    team_role, _created = TeamRole.objects.update_or_create(
        user=locked_user,
        defaults={"role": role},
    )

    managed_names = [value for value, _label in TeamRoleName.choices]
    locked_user.groups.remove(*Group.objects.filter(name__in=managed_names))
    locked_user.groups.add(Group.objects.get(name=role.value))

    if before_role != role.value:
        actor_role = TeamRole.objects.filter(user=actor).first() if actor else None
        AuditEvent.objects.create(
            actor_type=ActorType.USER if actor_role else ActorType.SYSTEM,
            actor_id=actor_role.pk if actor_role else None,
            action="accounts.team_role_assigned",
            object_type="team_role",
            object_id=team_role.pk,
            before_summary={"role": before_role},
            after_summary={"role": role.value},
            reason_key="team_access_change",
            request_id=request_id,
        )
    return team_role
