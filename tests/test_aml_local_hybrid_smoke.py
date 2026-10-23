"""Offline validation of the live smoke's strict evidence expectations."""

import copy
import json
from datetime import UTC, datetime

import pytest

from scripts.smoke_aml_local_hybrid import WRITES, validate_evidence


def response():
    return {
        "data": [
            {
                "id": f"{w['session_id']}-{i}",
                "content": json.dumps(
                    {
                        "source": {
                            "session_id": w["session_id"],
                            "turn_index": i,
                            "text": m["content"],
                            "transport_role": m["role"],
                            "speaker": "owner"
                            if m["role"] == "user"
                            else "historical_assistant",
                            "actor": "owner" if m["role"] == "user" else "agent",
                            "source_authority": "human_self"
                            if m["role"] == "user"
                            else "agent_output",
                            "observed_at": datetime.fromtimestamp(
                                m["timestamp"] / 1000, UTC
                            ).isoformat(),
                        }
                    }
                ),
            }
            for w in WRITES[:2]
            for i, m in enumerate(w["messages"])
        ]
    }


def test_live_validator_accepts_complete_sources_independent_of_order():
    value = response()
    validate_evidence(value)
    value["data"].reverse()
    validate_evidence(value)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "owner_leak",
        "actor",
        "authority",
        "timestamp",
        "rewrite",
    ],
)
def test_live_validator_rejects_source_binding_failures(fault):
    value = response()
    if fault == "missing":
        value["data"].pop()
    elif fault == "duplicate":
        value["data"][1] = copy.deepcopy(value["data"][0])
    else:
        target = value["data"][1]
        body = json.loads(target["content"])
        body["source"].update(
            {
                "owner_leak": {"text": "SECRET_B_KEEPER"},
                "actor": {"actor": "owner"},
                "authority": {"source_authority": "human_self"},
                "timestamp": {"observed_at": "2024-01-01T00:00:00+00:00"},
                "rewrite": {"text": "rewritten source"},
            }[fault]
        )
        target["content"] = json.dumps(body)
    with pytest.raises(AssertionError):
        validate_evidence(value)
