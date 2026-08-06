from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION jobs_reject_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'evidence catalogs and items are append-only' USING ERRCODE = '55000';
END;
$$;
"""

CREATE_TRIGGER_SQL = """
CREATE TRIGGER jobs_evidencecatalog_immutable
BEFORE UPDATE OR DELETE ON jobs_evidencecatalog
FOR EACH ROW EXECUTE FUNCTION jobs_reject_evidence_mutation();
CREATE TRIGGER jobs_evidenceitem_immutable
BEFORE UPDATE OR DELETE ON jobs_evidenceitem
FOR EACH ROW EXECUTE FUNCTION jobs_reject_evidence_mutation();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS jobs_evidencecatalog_immutable ON jobs_evidencecatalog;
DROP TRIGGER IF EXISTS jobs_evidenceitem_immutable ON jobs_evidenceitem;
"""

DROP_FUNCTION_SQL = "DROP FUNCTION IF EXISTS jobs_reject_evidence_mutation();"


def create_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION_SQL)
    schema_editor.execute(CREATE_TRIGGER_SQL)


def drop_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_TRIGGER_SQL)
    schema_editor.execute(DROP_FUNCTION_SQL)


class Migration(migrations.Migration):
    dependencies = [("jobs", "0006_evidencecatalog_evidenceitem_and_more")]

    operations = [migrations.RunPython(create_triggers, drop_triggers)]
