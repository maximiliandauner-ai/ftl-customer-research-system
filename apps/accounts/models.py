from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class TeamRoleName(models.TextChoices):
    ADMIN = "admin", "Admin"
    FOUNDER = "founder", "Founder"
    RESEARCHER = "researcher", "Researcher"
    REVIEWER = "reviewer", "Reviewer"
    VIEWER = "viewer", "Viewer"


class TeamRole(UUIDModel, TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="team_role",
    )
    role = models.CharField(max_length=20, choices=TeamRoleName.choices)

    class Meta:
        ordering = ("user__username",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=TeamRoleName.values),
                name="accounts_team_role_known",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.get_username()} — {self.get_role_display()}"
