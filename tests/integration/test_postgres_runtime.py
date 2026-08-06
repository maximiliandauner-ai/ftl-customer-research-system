import pytest
from django.core.management import call_command
from django.db import connection


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_canonical_database_and_migrations_are_available() -> None:
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('server_version_num')::integer")
        version_number = cursor.fetchone()[0]

    assert version_number >= 180000
    call_command("migrations_applied_check", verbosity=0)
