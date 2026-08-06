from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION signals_reject_assessment_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'signal assessment evidence links are append-only' USING ERRCODE = '55000';
END;
$$;
"""

CREATE_TRIGGER_SQL = """
CREATE TRIGGER signals_signalassessmentevidence_immutable
BEFORE UPDATE OR DELETE ON signals_signalassessmentevidence
FOR EACH ROW EXECUTE FUNCTION signals_reject_assessment_evidence_mutation();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS signals_signalassessmentevidence_immutable
ON signals_signalassessmentevidence;
"""

DROP_FUNCTION_SQL = "DROP FUNCTION IF EXISTS signals_reject_assessment_evidence_mutation();"


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
    dependencies = [("signals", "0004_signalassessment_capabilitygaprecord_and_more")]

    operations = [migrations.RunPython(create_trigger, drop_trigger)]
