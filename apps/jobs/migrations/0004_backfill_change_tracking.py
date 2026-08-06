import re

import django.db.models.deletion
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_TRIGGER_SQL = """
CREATE TRIGGER jobs_postingchangeevent_immutable
BEFORE UPDATE OR DELETE ON jobs_postingchangeevent
FOR EACH ROW EXECUTE FUNCTION jobs_reject_immutable_snapshot_mutation();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS jobs_postingchangeevent_immutable ON jobs_postingchangeevent;
"""


def normalize_title(value: str) -> str:
    return " ".join(re.split(r"\s+", value.strip())).casefold()


def backfill_change_tracking(apps: Apps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    job_posting = apps.get_model("jobs", "JobPosting")
    observation = apps.get_model("jobs", "PostingObservation")
    for posting in job_posting.objects.filter(normalized_title="").iterator(chunk_size=500):
        posting.normalized_title = normalize_title(posting.title)
        posting.save(update_fields=("normalized_title",))
    for item in observation.objects.filter(fetch_attempt__isnull=True).select_related(
        "source_snapshot"
    ):
        item.fetch_attempt_id = item.source_snapshot.fetch_attempt_id
        item.save(update_fields=("fetch_attempt",))


def reverse_backfill(_apps: Apps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    return


def create_event_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE_TRIGGER_SQL)


def drop_event_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP_TRIGGER_SQL)


class Migration(migrations.Migration):
    dependencies = [("jobs", "0003_duplicaterelationship_postingchangeevent_and_more")]

    operations = [
        migrations.RunPython(backfill_change_tracking, reverse_backfill),
        migrations.AlterField(
            model_name="postingobservation",
            name="fetch_attempt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="posting_observations",
                to="sources.fetchattempt",
            ),
        ),
        migrations.RunPython(create_event_trigger, drop_event_trigger),
    ]
