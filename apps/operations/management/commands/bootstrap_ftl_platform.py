import hashlib
import json
from datetime import date

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from apps.accounts.models import TeamRoleName
from apps.accounts.policy import ROLE_PERMISSION_KEYS
from apps.discovery.contracts import SearchDefinitionInputV2
from apps.discovery.models import EndpointWatch
from apps.discovery.services import create_definition_version
from apps.providers.models import CapabilityStatus, ModelCapability, ModelPolicy
from apps.signals.services import ensure_default_ontology
from apps.sources.models import EndpointStatus, SourceEndpoint

DISCOVERY_POLICY_REFERENCE = (
    "https://developers.openai.com/api/docs/guides/tools-web-search; "
    "https://developers.openai.com/api/docs/guides/structured-outputs; "
    "https://developers.openai.com/api/docs/models/gpt-5.6-terra"
)


def _sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class Command(BaseCommand):
    help = "Idempotently seed FTL roles, permissions, and safe platform schedules."

    @transaction.atomic
    def handle(self, *_args: object, **_options: object) -> None:
        group_count = 0
        for role in TeamRoleName:
            group, created = Group.objects.get_or_create(name=role.value)
            permission_keys = ROLE_PERMISSION_KEYS[role]
            query = Q(pk__in=[])
            for app_label, codename in permission_keys:
                query |= Q(content_type__app_label=app_label, codename=codename)
            permissions = Permission.objects.filter(query)
            found = {
                (permission.content_type.app_label, permission.codename)
                for permission in permissions.select_related("content_type")
            }
            missing = set(permission_keys) - found
            if missing:
                raise CommandError(
                    "Missing platform permissions after migration: "
                    + ", ".join(f"{app}.{code}" for app, code in sorted(missing))
                    + "."
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
        discovery_schedule, _created = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="6",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="Europe/Berlin",
        )
        PeriodicTask.objects.update_or_create(
            name="FTL daily source discovery",
            defaults={
                "task": "discovery.schedule_daily",
                "interval": None,
                "crontab": discovery_schedule,
                "queue": "discovery",
                "enabled": True,
                "args": "[]",
                "kwargs": "{}",
            },
        )

        capability, _created = ModelCapability.objects.update_or_create(
            model_id="gpt-5.6-terra",
            defaults={
                "status": CapabilityStatus.ACTIVE,
                "supports_responses": True,
                "supports_structured_outputs": True,
                "supports_web_search": True,
                "web_search_tool_type": "web_search",
                "supports_source_list_include": True,
                "supports_background": True,
                "supports_background_store_false": False,
                "supports_reasoning_effort": True,
                "allowed_reasoning_efforts": ["low", "medium", "high", "xhigh"],
                "supports_store_false": True,
                "maximum_tool_calls": 50,
                "effective_from": date(2026, 8, 5),
                "official_reference_snapshot": DISCOVERY_POLICY_REFERENCE,
            },
        )
        policy_values = {
            "stage": "discovery.web_search",
            "capability_id": str(capability.pk),
            "reasoning_effort": "medium",
            "tool_type": "web_search",
            "search_context_size": "medium",
            "max_tool_calls": 8,
            "max_output_tokens": 4_000,
            "max_cost_usd": "0.5000",
            "max_daily_cost_usd": "5.0000",
            "max_monthly_cost_usd": "100.0000",
            "max_concurrent_calls": 2,
            "store": False,
        }
        policy_hash = _sha256(policy_values)
        ModelPolicy.objects.filter(
            policy_key="discovery.standard_web",
            active=True,
        ).exclude(version="1.0.0").update(active=False)
        policy, policy_created = ModelPolicy.objects.get_or_create(
            policy_key="discovery.standard_web",
            version="1.0.0",
            defaults={
                "stage": policy_values["stage"],
                "capability": capability,
                "reasoning_effort": policy_values["reasoning_effort"],
                "tool_type": policy_values["tool_type"],
                "search_context_size": policy_values["search_context_size"],
                "max_tool_calls": policy_values["max_tool_calls"],
                "max_output_tokens": policy_values["max_output_tokens"],
                "max_cost_usd": policy_values["max_cost_usd"],
                "max_daily_cost_usd": policy_values["max_daily_cost_usd"],
                "max_monthly_cost_usd": policy_values["max_monthly_cost_usd"],
                "max_concurrent_calls": policy_values["max_concurrent_calls"],
                "store": policy_values["store"],
                "active": True,
                "policy_sha256": policy_hash,
            },
        )
        if not policy_created and policy.policy_sha256 != policy_hash:
            raise CommandError(
                "Model policy discovery.standard_web/1.0.0 is immutable and differs "
                "from the reviewed bootstrap policy. Create a new policy version."
            )
        if not policy.active:
            policy.active = True
            policy.save(update_fields=("active",))

        for policy_key, values in (
            (
                "research.standard_web",
                {
                    "stage": "research.web_search",
                    "reasoning_effort": "medium",
                    "tool_type": "web_search",
                    "search_context_size": "medium",
                    "max_tool_calls": 18,
                    "max_output_tokens": 8_000,
                    "max_cost_usd": "1.5000",
                    "max_daily_cost_usd": "5.0000",
                    "max_monthly_cost_usd": "100.0000",
                    "max_concurrent_calls": 1,
                    "store": False,
                },
            ),
            (
                "research.standard_extract",
                {
                    "stage": "research.extract",
                    "reasoning_effort": "medium",
                    "tool_type": "",
                    "search_context_size": "medium",
                    "max_tool_calls": 1,
                    "max_output_tokens": 6_000,
                    "max_cost_usd": "0.5000",
                    "max_daily_cost_usd": "5.0000",
                    "max_monthly_cost_usd": "100.0000",
                    "max_concurrent_calls": 1,
                    "store": False,
                },
            ),
        ):
            version = "1.0.0"
            immutable_values = {**values, "capability_id": str(capability.pk)}
            reviewed_hash = _sha256(immutable_values)
            ModelPolicy.objects.filter(policy_key=policy_key, active=True).exclude(
                version=version
            ).update(active=False)
            research_policy, research_policy_created = ModelPolicy.objects.get_or_create(
                policy_key=policy_key,
                version=version,
                defaults={
                    **values,
                    "capability": capability,
                    "active": True,
                    "policy_sha256": reviewed_hash,
                },
            )
            if not research_policy_created and research_policy.policy_sha256 != reviewed_hash:
                raise CommandError(
                    f"Model policy {policy_key}/{version} is immutable and differs "
                    "from the reviewed bootstrap policy. Create a new policy version."
                )
            if not research_policy.active:
                research_policy.active = True
                research_policy.save(update_fields=("active",))

        create_definition_version(
            SearchDefinitionInputV2(
                definition_key="ftl-capability-demand",
                name="FTL capability demand",
                description=(
                    "Public employer and ATS job sources indicating demand for workflow, "
                    "knowledge, data, and AI-enabled operating capabilities."
                ),
                query_template="({{role_terms}}) ({{capability_terms}}) ({{location_terms}})",
                language="en",
                countries=("DE", "AT", "CH"),
                locations=("Germany", "Austria", "Switzerland", "Remote"),
                capability_clusters=(
                    "workflow automation",
                    "knowledge systems",
                    "data integration",
                    "AI-enabled operations",
                ),
                positive_terms=(
                    "workflow automation",
                    "process automation",
                    "knowledge management",
                    "data integration",
                    "AI agent",
                    "revenue operations",
                    "customer operations",
                ),
                negative_terms=("recruitment agency", "staffing agency"),
                preferred_domains=(
                    "jobs.personio.com",
                    "boards.greenhouse.io",
                    "jobs.lever.co",
                    "jobs.ashbyhq.com",
                ),
                excluded_domains=(
                    "linkedin.com",
                    "xing.com",
                    "facebook.com",
                ),
                source_type_filters=(
                    "job_posting",
                    "career_page",
                    "personio",
                    "greenhouse",
                    "lever",
                    "ashby",
                ),
                schedule_key="daily_morning",
                max_candidates=50,
                lookback_days=21,
            ),
            actor=None,
        )
        now = timezone.now()
        watch_count = 0
        for endpoint in SourceEndpoint.objects.filter(status=EndpointStatus.ACTIVE):
            _watch, created = EndpointWatch.objects.get_or_create(
                source_endpoint=endpoint,
                defaults={"next_poll_at": now},
            )
            watch_count += int(created)
        ensure_default_ontology()
        self.stdout.write(
            self.style.SUCCESS(
                "FTL platform policy ready: "
                f"5 roles ({group_count} new), 3 schedules, {watch_count} new watches."
            )
        )
