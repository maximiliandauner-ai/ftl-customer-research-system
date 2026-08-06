from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max

from apps.knowledge.contracts import KnowledgeCatalogV2
from apps.knowledge.models import (
    ApprovedClaim,
    Asset,
    KnowledgeActivationEvent,
    KnowledgeRegistryState,
    KnowledgeRelease,
    OfferModule,
    ProhibitedClaim,
)
from apps.operations.models import ActorType, AuditEvent
from apps.sources.policy import canonicalize_url

SOURCE_FILES = (
    "offers/offers.json",
    "company/approved_claims.json",
    "company/prohibited_claims.json",
    "assets/assets.json",
)
MAX_SOURCE_BYTES = 2_000_000
COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")


class KnowledgeValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SyncedKnowledge:
    release: KnowledgeRelease
    created: bool


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: object) -> str:
    return _hash(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )


def _read_json(root: Path, relative: str) -> tuple[object, dict[str, object]]:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path.is_symlink():
        raise KnowledgeValidationError("Knowledge source paths must remain inside the source root.")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise KnowledgeValidationError(
            f"Unable to read required knowledge file: {relative}."
        ) from exc
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise KnowledgeValidationError(
            f"Knowledge file {relative} is empty or exceeds the 2 MB limit."
        )
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise KnowledgeValidationError(f"Knowledge file {relative} is not valid JSON.") from exc
    return payload, {"path": relative, "sha256": _hash(raw), "size_bytes": len(raw)}


def load_knowledge_catalog(root: Path) -> tuple[KnowledgeCatalogV2, dict[str, object]]:
    payloads: dict[str, object] = {}
    manifest_files: list[dict[str, object]] = []
    for relative in SOURCE_FILES:
        payload, metadata = _read_json(root, relative)
        payloads[relative] = payload
        manifest_files.append(metadata)
    catalog_payload = {
        "schema_version": "2.1",
        "offers": payloads["offers/offers.json"],
        "approved_claims": payloads["company/approved_claims.json"],
        "prohibited_claims": payloads["company/prohibited_claims.json"],
        "assets": payloads["assets/assets.json"],
    }
    try:
        catalog = KnowledgeCatalogV2.model_validate_json(json.dumps(catalog_payload))
    except Exception as exc:
        raise KnowledgeValidationError("The knowledge catalog failed its strict schema.") from exc
    _validate_catalog(catalog)
    manifest: dict[str, object] = {
        "schema_version": "2.1",
        "files": sorted(manifest_files, key=lambda item: str(item["path"])),
        "catalog_sha256": _canonical_hash(catalog.model_dump(mode="json")),
    }
    return catalog, manifest


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise KnowledgeValidationError(f"The knowledge catalog has duplicate {label} keys.")


def _validate_catalog(catalog: KnowledgeCatalogV2) -> None:
    _unique([item.key for item in catalog.offers], "offer")
    _unique([item.claim_key for item in catalog.approved_claims], "approved claim")
    _unique([item.claim_key for item in catalog.prohibited_claims], "prohibited claim")
    _unique([item.asset_id for item in catalog.assets], "asset")
    asset_ids = {item.asset_id for item in catalog.assets}
    for claim in catalog.approved_claims:
        if claim.review_due_at < claim.valid_from:
            raise KnowledgeValidationError("An approved claim is due before it becomes valid.")
        if not set(claim.supporting_asset_ids).issubset(asset_ids):
            raise KnowledgeValidationError("An approved claim references an unknown asset.")
    for asset in catalog.assets:
        canonical = canonicalize_url(asset.public_url, settings.RUNTIME_SETTINGS.fetch)
        try:
            ipaddress.ip_address(canonical.hostname_ascii)
        except ValueError:
            pass
        else:
            raise KnowledgeValidationError("Literal-IP asset URLs are prohibited.")
        if asset.confidentiality != "public" and asset.approved_for_external_use:
            raise KnowledgeValidationError(
                "Only public assets may be marked approved for external use."
            )


@transaction.atomic
def sync_knowledge_release(
    *, source_root: Path, source_commit: str, actor: User | None
) -> SyncedKnowledge:
    normalized_commit = source_commit.strip().casefold()
    if not COMMIT_RE.fullmatch(normalized_commit):
        raise KnowledgeValidationError("The source commit must be a 7-64 character hex SHA.")
    catalog, manifest = load_knowledge_catalog(source_root)
    manifest_hash = _canonical_hash(manifest)
    existing = KnowledgeRelease.objects.filter(
        source_commit=normalized_commit, manifest_sha256=manifest_hash
    ).first()
    if existing is not None:
        return SyncedKnowledge(release=existing, created=False)
    version = (KnowledgeRelease.objects.aggregate(value=Max("version"))["value"] or 0) + 1
    release = KnowledgeRelease.objects.create(
        version=version,
        source_commit=normalized_commit,
        schema_version="2.1",
        manifest_sha256=manifest_hash,
        source_manifest=manifest,
        item_counts={
            "offers": len(catalog.offers),
            "approved_claims": len(catalog.approved_claims),
            "prohibited_claims": len(catalog.prohibited_claims),
            "assets": len(catalog.assets),
        },
        synced_by=actor,
    )
    OfferModule.objects.bulk_create(
        [
            OfferModule(
                release=release,
                key=item.key,
                version=item.version,
                title=item.title,
                ftl_layers=list(item.ftl_layers),
                problem_patterns=list(item.problem_patterns),
                description=item.description,
                typical_deliverables=list(item.typical_deliverables),
                suitable_client_profiles=list(item.suitable_client_profiles),
                infrastructure_options=list(item.infrastructure_options),
                exclusions=list(item.exclusions),
                approved=item.approved,
            )
            for item in catalog.offers
        ]
    )
    ApprovedClaim.objects.bulk_create(
        [
            ApprovedClaim(
                release=release,
                claim_key=item.claim_key,
                version=item.version,
                full_wording=item.full_wording,
                short_wording=item.short_wording,
                claim_type=item.claim_type,
                supporting_asset_ids=list(item.supporting_asset_ids),
                allowed_audiences=list(item.allowed_audiences),
                allowed_languages=list(item.allowed_languages),
                paraphrase_allowed=item.paraphrase_allowed,
                strengthening_prohibited=item.strengthening_prohibited,
                valid_from=item.valid_from,
                review_due_at=item.review_due_at,
            )
            for item in catalog.approved_claims
        ]
    )
    ProhibitedClaim.objects.bulk_create(
        [
            ProhibitedClaim(
                release=release,
                claim_key=item.claim_key,
                wording=item.wording,
                reason=item.reason,
            )
            for item in catalog.prohibited_claims
        ]
    )
    assets: list[Asset] = []
    for item in catalog.assets:
        canonical = canonicalize_url(item.public_url, settings.RUNTIME_SETTINGS.fetch)
        assets.append(
            Asset(
                release=release,
                asset_id=item.asset_id,
                version=item.version,
                title=item.title,
                asset_type=item.type,
                public_url=canonical.canonical,
                public_url_sha256=canonical.sha256,
                short_description=item.short_description,
                detailed_description=item.detailed_description,
                capability_tags=list(item.capability_tags),
                ftl_layers=list(item.ftl_layers),
                industries=list(item.industries),
                languages=list(item.languages),
                audiences=list(item.audiences),
                confidentiality=item.confidentiality,
                approved_for_external_use=item.approved_for_external_use,
                status=item.status,
                last_reviewed_at=item.last_reviewed_at,
                url_last_checked_at=item.url_last_checked_at,
            )
        )
    Asset.objects.bulk_create(assets)
    AuditEvent.objects.create(
        actor_type=ActorType.USER if actor else ActorType.SYSTEM,
        action="knowledge.release_synced",
        object_type="knowledge_release",
        object_id=release.pk,
        after_summary={
            "version": release.version,
            "manifest_sha256": release.manifest_sha256,
            "item_counts": release.item_counts,
        },
        reason_key="validated_editorial_sync",
    )
    return SyncedKnowledge(release=release, created=True)


def active_knowledge_release() -> KnowledgeRelease | None:
    state = (
        KnowledgeRegistryState.objects.select_related("active_release")
        .filter(registry_key="default")
        .first()
    )
    return state.active_release if state else None


@transaction.atomic
def activate_knowledge_release(
    *, release_id: UUID, actor: User, reason: str
) -> KnowledgeActivationEvent:
    normalized_reason = " ".join(reason.split())[:500]
    if len(normalized_reason) < 5:
        raise KnowledgeValidationError("Activation reason must be at least five characters.")
    release = KnowledgeRelease.objects.get(pk=release_id)
    KnowledgeRegistryState.objects.get_or_create(registry_key="default")
    state = KnowledgeRegistryState.objects.select_for_update().get(registry_key="default")
    if state.active_release_id == release.pk:
        prior_event = KnowledgeActivationEvent.objects.filter(activated_release=release).first()
        if prior_event is None:
            raise KnowledgeValidationError("The registry state lacks an activation event.")
        return cast(KnowledgeActivationEvent, prior_event)
    prior = state.active_release
    event = KnowledgeActivationEvent.objects.create(
        prior_release=prior,
        activated_release=release,
        actor=actor,
        reason=normalized_reason,
    )
    state.active_release = release
    state.row_version += 1
    state.save(update_fields=("active_release", "row_version", "updated_at"))
    AuditEvent.objects.create(
        actor_type=ActorType.USER,
        action="knowledge.release_activated",
        object_type="knowledge_release",
        object_id=release.pk,
        before_summary={"active_release_id": str(prior.pk) if prior else None},
        after_summary={
            "active_release_id": str(release.pk),
            "manifest_sha256": release.manifest_sha256,
        },
        reason_key=normalized_reason,
    )
    try:
        from apps.solutions.services import invalidate_for_knowledge_release
    except ImportError:
        pass
    else:
        invalidate_for_knowledge_release(active_release_id=release.pk)
    return event
