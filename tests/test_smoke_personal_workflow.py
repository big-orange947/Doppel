"""Configuration guards for opt-in PG smoke; no model loading or network."""

import pytest

from scripts.smoke_personal_workflow import storage_identity


def test_storage_identity_binds_database_schema_and_host_without_password():
    original = storage_identity(
        "postgresql://user:secret-a@localhost:5432/memory", "doppel_workflow_a"
    )
    assert original == storage_identity(
        "postgresql://user:secret-b@localhost/memory", "doppel_workflow_a"
    )
    assert original != storage_identity(
        "postgresql://user:secret-a@localhost/another", "doppel_workflow_a"
    )
    assert original != storage_identity(
        "postgresql://user:secret-a@localhost/memory", "doppel_workflow_b"
    )
    assert original != storage_identity(
        "postgresql://user:secret-a@other/memory", "doppel_workflow_a"
    )
    assert "secret" not in original


@pytest.mark.parametrize(
    "url",
    [
        "",
        "dbname=memory",
        "https://localhost/memory",
        "postgresql://localhost",
        "postgresql://localhost/memory?host=other",
        "postgresql://localhost/memory#fragment",
    ],
)
def test_ambiguous_dsn_fails_before_connection(url):
    with pytest.raises(ValueError):
        storage_identity(url, "doppel_workflow_a")
