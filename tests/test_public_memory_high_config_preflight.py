from copy import deepcopy

import pytest

from benchmarks.public_memory_high_config_preflight import (
    _IdentityOnlyEmbedding,
    bound_scopes,
)
from benchmarks.public_memory_pilot import _hash
from integrations.aml.contract import memory_scope


def fixture():
    scope = memory_scope("run", "user")
    manifest = {
        "run_namespace": "run",
        "cases": [
            {"scope_key": scope.scope_key, "partition": "diagnostic"},
            {"scope_key": "reserved", "partition": "reserved"},
        ],
    }
    plan = {"chunks": [{"user_id": "user", "scope_key": scope.scope_key}]}
    plan["plan_fingerprint"] = _hash(plan)
    return manifest, {
        "plan": plan,
        "postgres_schema": "public_memory_" + plan["plan_fingerprint"][:12],
    }


def test_scope_binding_excludes_reserved_and_preserves_inputs():
    manifest, ingestion = fixture()
    before = deepcopy((manifest, ingestion))
    assert bound_scopes(manifest, ingestion) == [memory_scope("run", "user")]
    assert (manifest, ingestion) == before


@pytest.mark.parametrize(
    "mutation", ["fingerprint", "schema", "namespace", "scope", "reserved"]
)
def test_invalid_binding_rejected(mutation):
    manifest, ingestion = fixture()
    if mutation == "fingerprint":
        ingestion["plan"]["plan_fingerprint"] = "wrong"
    elif mutation == "schema":
        ingestion["postgres_schema"] = "other_schema"
    elif mutation == "namespace":
        manifest["run_namespace"] = "other"
    elif mutation == "scope":
        ingestion["plan"]["chunks"][0]["scope_key"] = "other"
    else:
        manifest["cases"][0]["partition"] = "reserved"
    with pytest.raises(ValueError):
        bound_scopes(manifest, ingestion)


@pytest.mark.asyncio
async def test_readiness_cannot_invoke_embedding():
    provider = _IdentityOnlyEmbedding(
        {"name": "synthetic", "version": "1", "dimensions": 2}
    )
    with pytest.raises(RuntimeError, match="forbidden"):
        await provider.embed(["text"])
