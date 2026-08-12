from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

CREATE_FUNCTION_SQL = """
CREATE FUNCTION companies_reject_profile_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'company profile evidence records are append-only' USING ERRCODE = '55000';
END;
$$;
"""

TABLES = (
    "companies_companyprofilesource",
    "companies_companyfieldobservation",
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
            FOR EACH ROW EXECUTE FUNCTION companies_reject_profile_evidence_mutation();
            """
        )


def drop_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
    schema_editor.execute("DROP FUNCTION IF EXISTS companies_reject_profile_evidence_mutation();")


class Migration(migrations.Migration):
    dependencies = [("companies", "0003_companyprofilerun_companyprofilesource_and_more")]

    operations = [migrations.RunPython(create_triggers, drop_triggers)]
