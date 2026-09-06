"""Contract tests only: fake decisions do not measure model quality."""
import asyncio

import pytest

from doppel_memory.evidence import (
    EvidenceDecision,
    EvidenceItem,
    EvidenceRequest,
    EvidenceResponse,
    EvidenceVerificationConfig,
    ReferenceEvidenceVerifier,
    verify_evidence,
)


class Verifier:
    def __init__(self, mode="supported"):
        self.mode = mode
        self.calls = []

    async def verify(self, request):
        self.calls.append(request)
        if self.mode == "error":
            raise RuntimeError("private-secret")
        if self.mode == "timeout":
            await asyncio.sleep(10)
        decisions = [EvidenceDecision(item_id=i.item_id, verdict="supported")
                     for i in request.items]
        if self.mode == "missing":
            decisions = []
        elif self.mode == "duplicate":
            decisions *= 2
        elif self.mode == "unknown":
            decisions[0] = EvidenceDecision(item_id="foreign", verdict="supported")
        elif self.mode in {"unsupported", "uncertain"}:
            decisions = [EvidenceDecision(item_id=i.item_id, verdict=self.mode)
                         for i in request.items]
        return EvidenceResponse(decisions=decisions)


def request():
    return EvidenceRequest(question="Who?", items=[
        EvidenceItem(item_id=f"item_{i}", content="Evidence") for i in range(3)
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown", "error", "timeout"])
async def test_fail_closed(mode):
    decisions, summary = await verify_evidence(
        Verifier(mode), request(), EvidenceVerificationConfig(timeout_seconds=.01)
    )
    assert decisions == {}
    assert summary.status == "unavailable"
    assert "private-secret" not in summary.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["supported", "unsupported", "uncertain"])
async def test_closed_verdicts_batched(mode):
    verifier = Verifier(mode)
    decisions, summary = await verify_evidence(
        verifier, request(), EvidenceVerificationConfig(batch_size=2)
    )
    assert len(verifier.calls) == 2
    assert set(decisions.values()) == {mode}
    assert getattr(summary, mode) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [
    EvidenceVerificationConfig(max_candidates=2),
    EvidenceVerificationConfig(max_input_chars=1),
])
async def test_limits_before_calls(config):
    verifier = Verifier()
    decisions, summary = await verify_evidence(verifier, request(), config)
    assert decisions == {} and summary.status == "limit_exceeded"
    assert verifier.calls == []


@pytest.mark.asyncio
async def test_empty_no_call_and_cancellation_propagates():
    verifier = Verifier()
    _, summary = await verify_evidence(
        verifier, EvidenceRequest(question="", items=[]), EvidenceVerificationConfig()
    )
    assert summary.status == "not_run" and not verifier.calls
    task = asyncio.create_task(verify_evidence(
        Verifier("timeout"), request(), EvidenceVerificationConfig()
    ))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_reference_schema_and_question():
    class Model:
        async def generate(self, req):
            assert req.input == request().model_dump()
            assert "decisions" in req.output_schema["properties"]
            return {"decisions": []}
    assert (await ReferenceEvidenceVerifier(Model()).verify(request())).decisions == []


@pytest.mark.asyncio
async def test_later_bad_batch_discards_earlier_supported_decisions():
    class LaterFailure(Verifier):
        async def verify(self, request):
            if self.calls:
                self.mode = "missing"
            return await super().verify(request)
    verifier = LaterFailure()
    decisions, summary = await verify_evidence(
        verifier, request(), EvidenceVerificationConfig(batch_size=2)
    )
    assert len(verifier.calls) == 2
    assert decisions == {} and summary.status == "unavailable"
