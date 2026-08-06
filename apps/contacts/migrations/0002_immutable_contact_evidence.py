from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

FUNCTION_SQL = """
CREATE FUNCTION contacts_reject_record_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'contact evidence and history records are append-only' USING ERRCODE = '55000';
END;
$$;
"""

TABLES = (
    "contacts_buyerroleresult",
    "contacts_buyerrolehypothesis",
    "contacts_contactsourceartifact",
    "contacts_contactevidence",
    "contacts_contactobservation",
    "contacts_suppressionentry",
    "contacts_contactselection",
)


def create_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FUNCTION_SQL)
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION contacts_reject_record_mutation();"
        )


def drop_triggers(_apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
    schema_editor.execute("DROP FUNCTION IF EXISTS contacts_reject_record_mutation();")


class Migration(migrations.Migration):
    dependencies = [("contacts", "0001_initial")]

    operations = [migrations.RunPython(create_triggers, drop_triggers)]
