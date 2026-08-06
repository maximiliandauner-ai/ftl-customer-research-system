from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION sources_reject_immutable_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'source artifact and snapshot records are append-only'
        USING ERRCODE = '55000';
END;
$$;
"""

CREATE_ARTIFACT_TRIGGER_SQL = """
CREATE TRIGGER sources_sourceartifact_immutable
BEFORE UPDATE OR DELETE ON sources_sourceartifact
FOR EACH ROW EXECUTE FUNCTION sources_reject_immutable_record_mutation();
"""

CREATE_SNAPSHOT_TRIGGER_SQL = """
CREATE TRIGGER sources_sourcesnapshot_immutable
BEFORE UPDATE OR DELETE ON sources_sourcesnapshot
FOR EACH ROW EXECUTE FUNCTION sources_reject_immutable_record_mutation();
"""

DROP_TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS sources_sourceartifact_immutable ON sources_sourceartifact;
DROP TRIGGER IF EXISTS sources_sourcesnapshot_immutable ON sources_sourcesnapshot;
"""

DROP_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS sources_reject_immutable_record_mutation();
"""


def create_immutability_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION_SQL)
    schema_editor.execute(CREATE_ARTIFACT_TRIGGER_SQL)
    schema_editor.execute(CREATE_SNAPSHOT_TRIGGER_SQL)


def drop_immutability_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_TRIGGERS_SQL)
    schema_editor.execute(DROP_FUNCTION_SQL)


class Migration(migrations.Migration):
    dependencies = [("sources", "0001_initial")]

    operations = [migrations.RunPython(create_immutability_triggers, drop_immutability_triggers)]
