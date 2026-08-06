from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION signals_reject_evidence_link_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'signal evidence links are append-only' USING ERRCODE = '55000';
END;
$$;
"""

CREATE_TRIGGER_SQL = """
CREATE TRIGGER signals_signalevidence_immutable
BEFORE UPDATE OR DELETE ON signals_signalevidence
FOR EACH ROW EXECUTE FUNCTION signals_reject_evidence_link_mutation();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS signals_signalevidence_immutable ON signals_signalevidence;
"""

DROP_FUNCTION_SQL = "DROP FUNCTION IF EXISTS signals_reject_evidence_link_mutation();"


def create_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION_SQL)
    schema_editor.execute(CREATE_TRIGGER_SQL)


def drop_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_TRIGGER_SQL)
    schema_editor.execute(DROP_FUNCTION_SQL)


class Migration(migrations.Migration):
    dependencies = [("signals", "0001_initial")]

    operations = [migrations.RunPython(create_trigger, drop_trigger)]
