from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel


class ImmutableKnowledgeQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable knowledge records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable knowledge records cannot be deleted.")


class KnowledgeRelease(UUIDModel):
    version = models.PositiveIntegerField(unique=True)
    source_commit = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=16, default="2.1")
    manifest_sha256 = models.CharField(max_length=64, unique=True)
    source_manifest = models.JSONField(default=dict)
    item_counts = models.JSONField(default=dict)
    synced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="synced_knowledge_releases",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableKnowledgeQuerySet.as_manager()

    class Meta:
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(
                fields=("source_commit", "manifest_sha256"),
                name="knowledge_release_commit_manifest_unique",
            )
        ]
        permissions = [
            ("sync_knowledge", "Can sync a validated FTL knowledge release"),
            ("activate_knowledge", "Can activate an FTL knowledge release"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("KnowledgeRelease records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("KnowledgeRelease records are immutable.")


class KnowledgeRegistryState(models.Model):
    registry_key = models.CharField(max_length=32, primary_key=True, default="default")
    active_release = models.ForeignKey(
        KnowledgeRelease,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="active_registry_states",
    )
    row_version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.registry_key} / {self.active_release_id or 'no active release'}"


class OfferModule(UUIDModel):
    release = models.ForeignKey(KnowledgeRelease, on_delete=models.PROTECT, related_name="offers")
    key = models.CharField(max_length=100)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    ftl_layers = models.JSONField(default=list)
    problem_patterns = models.JSONField(default=list)
    description = models.TextField()
    typical_deliverables = models.JSONField(default=list)
    suitable_client_profiles = models.JSONField(default=list)
    infrastructure_options = models.JSONField(default=list)
    exclusions = models.JSONField(default=list)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableKnowledgeQuerySet.as_manager()

    class Meta:
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(
                fields=("release", "key"), name="knowledge_offer_release_key_unique"
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("OfferModule records are immutable.")
        super().save(*args, **kwargs)


class ApprovedClaim(UUIDModel):
    release = models.ForeignKey(
        KnowledgeRelease, on_delete=models.PROTECT, related_name="approved_claims"
    )
    claim_key = models.CharField(max_length=100)
    version = models.PositiveIntegerField()
    full_wording = models.TextField()
    short_wording = models.CharField(max_length=500)
    claim_type = models.CharField(max_length=32)
    supporting_asset_ids = models.JSONField(default=list)
    allowed_audiences = models.JSONField(default=list)
    allowed_languages = models.JSONField(default=list)
    paraphrase_allowed = models.BooleanField(default=False)
    strengthening_prohibited = models.BooleanField(default=True)
    valid_from = models.DateField()
    review_due_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableKnowledgeQuerySet.as_manager()

    class Meta:
        ordering = ("claim_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("release", "claim_key"),
                name="knowledge_claim_release_key_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ApprovedClaim records are immutable.")
        super().save(*args, **kwargs)


class ProhibitedClaim(UUIDModel):
    release = models.ForeignKey(
        KnowledgeRelease, on_delete=models.PROTECT, related_name="prohibited_claims"
    )
    claim_key = models.CharField(max_length=100)
    wording = models.TextField()
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableKnowledgeQuerySet.as_manager()

    class Meta:
        ordering = ("claim_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("release", "claim_key"),
                name="knowledge_prohibited_release_key_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ProhibitedClaim records are immutable.")
        super().save(*args, **kwargs)


class Asset(UUIDModel):
    release = models.ForeignKey(KnowledgeRelease, on_delete=models.PROTECT, related_name="assets")
    asset_id = models.CharField(max_length=100)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    asset_type = models.CharField(max_length=100)
    public_url = models.TextField()
    public_url_sha256 = models.CharField(max_length=64)
    short_description = models.CharField(max_length=500)
    detailed_description = models.TextField()
    capability_tags = models.JSONField(default=list)
    ftl_layers = models.JSONField(default=list)
    industries = models.JSONField(default=list)
    languages = models.JSONField(default=list)
    audiences = models.JSONField(default=list)
    confidentiality = models.CharField(max_length=32)
    approved_for_external_use = models.BooleanField(default=False)
    status = models.CharField(max_length=16)
    last_reviewed_at = models.DateTimeField()
    url_last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableKnowledgeQuerySet.as_manager()

    class Meta:
        ordering = ("asset_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("release", "asset_id"),
                name="knowledge_asset_release_id_unique",
            ),
            models.CheckConstraint(
                condition=Q(
                    confidentiality__in=(
                        "public",
                        "internal",
                        "confidential_client",
                        "embargoed",
                    )
                ),
                name="knowledge_asset_confidentiality_known",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("live", "preview", "archived")),
                name="knowledge_asset_status_known",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Asset records are immutable.")
        super().save(*args, **kwargs)


class KnowledgeActivationEvent(UUIDModel):
    prior_release = models.ForeignKey(
        KnowledgeRelease,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activation_events_as_prior",
    )
    activated_release = models.ForeignKey(
        KnowledgeRelease,
        on_delete=models.PROTECT,
        related_name="activation_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="knowledge_activation_events",
    )
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableKnowledgeQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("KnowledgeActivationEvent records are immutable.")
        super().save(*args, **kwargs)
