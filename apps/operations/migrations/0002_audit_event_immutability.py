from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION operations_reject_audit_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'operations_auditevent is append-only' USING ERRCODE = '55000';
END;
$$;
"""

CREATE_TRIGGER_SQL = """
CREATE TRIGGER operations_auditevent_immutable
BEFORE UPDATE OR DELETE ON operations_auditevent
FOR EACH ROW EXECUTE FUNCTION operations_reject_audit_event_mutation();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS operations_auditevent_immutable ON operations_auditevent;
"""

DROP_FUNCTION_SQL = """
DROP FUNCTION IF EXISTS operations_reject_audit_event_mutation();
"""


def create_audit_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION_SQL)
    schema_editor.execute(CREATE_TRIGGER_SQL)


def drop_audit_trigger(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(DROP_TRIGGER_SQL)
    schema_editor.execute(DROP_FUNCTION_SQL)


class Migration(migrations.Migration):
    dependencies = [("operations", "0001_initial")]

    operations = [migrations.RunPython(create_audit_trigger, drop_audit_trigger)]
