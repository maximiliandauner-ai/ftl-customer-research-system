from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION research_reject_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'research evidence records are append-only' USING ERRCODE = '55000';
END;
$$;
"""

TABLES = (
    "research_researchreportartifact",
    "research_researchsource",
    "research_researchclaim",
    "research_researchclaimsource",
    "research_researchclaimsignal",
    "research_researchclaimevidence",
    "research_researchdossier",
)


def create_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CREATE_FUNCTION_SQL)
    for table in TABLES:
        schema_editor.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION research_reject_evidence_mutation();
            """
        )


def drop_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
    schema_editor.execute("DROP FUNCTION IF EXISTS research_reject_evidence_mutation();")


class Migration(migrations.Migration):
    dependencies = [("research", "0001_initial")]

    operations = [migrations.RunPython(create_triggers, drop_triggers)]
