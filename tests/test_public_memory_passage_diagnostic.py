from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_passage_diagnostic as runner
from benchmarks.public_memory_answer_comparison import AnswerRow
from doppel_memory.models import FactAuthority, MemoryScope
from integrations.aml.passages import AttributedPassage


def item():
    p = AttributedPassage(
        scope_key="scope",
        memory_id="original",
        evidence_id="event",
        role="assistant",
        actor="agent",
        authority=FactAuthority.AGENT_OUTPUT,
        session_id="session",
        transport_turn_index=1,
        at=datetime(2026, 1, 1, tzinfo=UTC),
        text="source excerpt",
        similarity=0.5,
        passage_id="span",
        start=10,
        end=24,
        source_text_sha256="a" * 64,
        source_char_count=50,
    )
    return runner.passage_item(p)


def test_fragment_projection_preserves_unique_citation_and_original_binding():
    context = item()
    assert context["memory_id"] == "span" and context["source_memory_id"] == "original"
    assert context["role"] == "assistant" and context["authority"] == "agent_output"
    assert context["excerpt"] and context["source_events"] == ["event"]
    assert context["source_span"]["start"] == 10 and context["source_span"]["end"] == 24


def test_reader_sees_offsets_but_never_reference_answer_or_profile():
    runtime = SimpleNamespace(
        query=SimpleNamespace(
            query="generic question", reference_time=datetime(2026, 1, 2, tzinfo=UTC)
        )
    )
    scoring = SimpleNamespace(answer="PRIVATE_GOLD")
    row = AnswerRow(0, "id", "PRIVATE_PROFILE", runtime, scoring, (item(),))
    request = runner.reader_request(row)
    assert "source_span" in request.input["context_items"][0]
    assert (
        "PRIVATE_GOLD" not in request.model_dump_json()
        and "PRIVATE_PROFILE" not in request.model_dump_json()
    )


@pytest.mark.asyncio
async def test_saved_order_never_changes_sources_or_scope():
    scope = MemoryScope(user_id="owner", agent_id="a")
    strategy = runner.SavedOrder(scope, ["first", "second"])
    assert [
        r.memory_id for r in await strategy.search(None, "query", [scope], limit=1)
    ] == ["first"]
    with pytest.raises(ValueError):
        await strategy.search(
            None, "query", [MemoryScope(user_id="other", agent_id="a")]
        )


@pytest.mark.asyncio
async def test_six_reader_and_six_judge_budget_with_fake_provider(
    tmp_path, monkeypatch
):
    calls = []

    def factory(config, key, observer):
        class Fake:
            name = "test-only-no-http"
            version = "1"

            async def generate(self, request):
                calls.append(request)
                observer({"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
                if "reference_answer" in request.input:
                    return {"answer_correct": True, "rationale": "synthetic"}
                return {
                    "answer": "synthetic",
                    "cited_memory_ids": [
                        request.input["context_items"][0]["memory_id"]
                    ],
                    "abstained": False,
                }

        return Fake()

    selected, rows = [], []
    for index, case in enumerate(runner.CASES):
        runtime = SimpleNamespace(
            query=SimpleNamespace(
                query=f"generic {index}",
                reference_time=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        selected.append(
            (runtime, SimpleNamespace(case_id=case, answer=f"synthetic {index}"))
        )
        for profile in ("whole", "spans"):
            context = item() | {"memory_id": f"id-{case}-{profile}"}
            rows.append(
                {
                    "index": len(rows),
                    "case_id": case,
                    "profile": profile,
                    "context": [context],
                }
            )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-not-real")
    monkeypatch.setattr(runner, "_default_provider_factory", factory)
    args = SimpleNamespace(run_dir=tmp_path)
    result = await runner.answers(
        args, selected, {"rows": rows}, {"plan_fingerprint": "frozen"}
    )
    assert result["status"] == "complete" and len(result["rows"]) == 6
    assert all(v["attempts_reserved"] <= 6 for v in result["usage"].values())
    assert len(calls) <= 12
    assert all(r["checks"]["structurally_valid"] for r in result["rows"])
    with pytest.raises(FileExistsError):
        await runner.answers(
            args, selected, {"rows": rows}, {"plan_fingerprint": "frozen"}
        )
