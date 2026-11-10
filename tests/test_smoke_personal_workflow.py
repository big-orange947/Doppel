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


@pytest.mark.parametrize("enabled", [False, True])
async def test_reference_preflight_stops_without_opt_in_or_credentials(
    monkeypatch, enabled
):
    from types import SimpleNamespace

    import scripts.smoke_personal_workflow as smoke

    async def unexpected(*args, **kwargs):
        pytest.fail("preflight reached DB/model workflow")

    monkeypatch.setattr(smoke, "run", unexpected)
    for key in ["DOPPEL_MODEL", "DOPPEL_OPENAI_BASE_URL", "DOPPEL_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    report = await smoke.dispatch(
        SimpleNamespace(analyzer="reference", live_llm=enabled)
    )
    assert not report["passed"] and report["paid_calls"] == 0
    assert report["error_type"] == "ValueError"
