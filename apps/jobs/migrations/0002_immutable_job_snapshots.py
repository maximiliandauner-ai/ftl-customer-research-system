from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION jobs_reject_immutable_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'normalized job posting snapshots are append-only'
        USING ERRCODE = '55000';
END;
$$;
"""

CREATE_TRIGGER_SQL = """
CREATE TRIGGER jobs_jobpostingsnapshot_immutable
BEFORE UPDATE OR DELETE ON jobs_jobpostingsnapshot
FOR EACH ROW EXECUTE FUNCTION jobs_reject_immutable_snapshot_mutation();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS jobs_jobpostingsnapshot_immutable ON jobs_jobpostingsnapshot;
"""

DROP_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS jobs_reject_immutable_snapshot_mutation();
"""


def create_immutability_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION_SQL)
    schema_editor.execute(CREATE_TRIGGER_SQL)


def drop_immutability_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_TRIGGER_SQL)
    schema_editor.execute(DROP_FUNCTION_SQL)


class Migration(migrations.Migration):
    dependencies = [("jobs", "0001_initial")]

    operations = [migrations.RunPython(create_immutability_trigger, drop_immutability_trigger)]
