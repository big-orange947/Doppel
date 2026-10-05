"""Two-stage isolation and workflow tests, not model semantic-quality measurements."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from benchmarks import surface_review_calibration_v2 as v2
from benchmarks import surface_review_calibration_v3 as runner
from benchmarks.surface_review_controls import build_baseline_request, fingerprint
from benchmarks.surface_review_controls_v2 import build_controls as build_v2_controls
from benchmarks.surface_review_controls_v3 import build_controls
from benchmarks.surface_review_separated import (
    build_contract_request,
    build_literal_request,
    entity_aliases,
    validate_contract_review,
    validate_literal_reading,
)
from tests.test_surface_review_calibration import _response
from tests.test_surface_review_observations import (
    FakeProvider as V2FakeProvider,
)
from tests.test_surface_review_observations import (
    args_for as v2_args,
)
from tests.test_surface_review_observations import (
    make_reference,
)


def literal_fixture(control: Any) -> dict[str, Any]:
    """Idealized offline oracle; private labels stay in TESTS, never provider input."""
    base = build_baseline_request(control)
    request = build_literal_request(base)
    aliases = entity_aliases(base)
    by_key = {v["surface_key"]: (ref, v["display_name"]) for ref, v in aliases.items()}
    memories = {m["surface_key"]: m for m in control.reviewer_input["memories"]}
    surfaces = []
    for t in request.input["texts"]:
        mode, frames = "not_a_query", []
        if t["field"] == "authored_query":
            mode = "neutral"
            if not control.acceptable and "answer_leak" in control.allowed_issue_codes:
                mode = (
                    "answerability_declaration"
                    if control.family == "permitted_confirmation_contract"
                    else "candidate_answer"
                )
            elif control.family == "permitted_confirmation_contract":
                mode = "candidate_answer"
        else:
            relation = memories[t["surface_key"]].get("relation")
            frame = {
                "kind": "other",
                "quote": t["text"],
                "action_quote": t["text"],
                "actor": {},
                "affected": {},
                "negated": False,
            }
            if relation:
                source, target = (
                    by_key[relation["source_entity_key"]],
                    by_key[relation["target_entity_key"]],
                )
                kind = {
                    "HELD_BY": "custody",
                    "WORKS_AT": "employment",
                    "ISSUED_BY": "issuance",
                }[relation["type"]]
                actor, affected = (
                    (source, target) if kind == "employment" else (target, source)
                )
                reverse = not control.acceptable and (
                    control.family
                    in {
                        "relation_direction",
                        "passive_and_active_custody",
                        "fronted_workplace_roles",
                    }
                    or control.family == "independent_content_edge_roles"
                    and t["field"] == "authored_edge_fact"
                )
                if reverse:
                    actor, affected = affected, actor
                if (
                    control.family == "edge_content_meaning"
                    and not control.acceptable
                    and t["field"] == "authored_edge_fact"
                ):
                    kind = "sale"
                frame.update(
                    kind=kind,
                    actor={"ref": actor[0], "quote": actor[1]},
                    affected={"ref": affected[0], "quote": affected[1]},
                )
            frames = [frame]
        surfaces.append(
            {
                "surface_key": t["surface_key"],
                "field": t["field"],
                "status": "parsed",
                "query_mode": mode,
                "quote": t["text"],
                "frames": frames,
            }
        )
    return {"surfaces": surfaces}


def contract_fixture(control: Any, *, issues: bool = True) -> dict[str, Any]:
    raw = _response(control, True)
    if not issues:
        raw["issues"] = []
    slots = {
        s["surface_key"]: s
        for k in ("entities", "memories", "queries")
        for s in control.reviewer_input[k]
    }
    for issue in raw["issues"]:
        slot = slots[issue["surface_key"]]
        issue["citations"].append(
            {
                "surface_key": issue["surface_key"],
                "field": "semantic_brief",
                "quote": slot["semantic_brief"],
            }
        )
    raw["query_contracts"] = [
        {
            "surface_key": q["surface_key"],
            "contract": "confirmation_allowed"
            if control.family == "permitted_confirmation_contract"
            else "neutral_required",
            "brief_quote": q["semantic_brief"],
        }
        for q in control.reviewer_input["queries"]
    ]
    return raw


def test_taxonomy_audit_keeps_surfaces_and_previous_scores_immutable() -> None:
    old, new = build_v2_controls(), build_controls()
    for a, b in zip(old, new, strict=True):
        assert build_baseline_request(a) == build_baseline_request(b)
        assert a.allowed_issue_keys == b.allowed_issue_keys
        assert b.allowed_issue_codes == a.allowed_issue_codes + (
            ["temporal_mismatch"]
            if a.family == "old_current_custody" and not a.acceptable
            else []
        )
    assert (
        fingerprint(old)
        == "1e04c7658cad564f3498b6f3278e374fb950912073690a2182f9cdc12d00f9d9"
    )
    assert (
        fingerprint(new)
        == "5edbc08f654678067230aa9c87e7be3171b1ab731c7737675edf2fb015c8ed79"
    )
    issue = {
        "surface_key": "memory-a",
        "issue_code": "temporal_mismatch",
        "detail": "有效期重叠。",
    }
    assert not v2.v1.score_review(old[5], [issue])["correct"]
    assert v2.v1.score_review(new[5], [issue])["correct"]


def test_literal_request_is_invariant_to_all_withheld_contract_information() -> None:
    for control in build_controls():
        base = build_baseline_request(control)
        changed = deepcopy(base.input)
        changed["review_nonce"] = "hidden-contract-nonce"
        changed["relation_meanings"] = {"x": "another expected interpretation"}
        for e in changed["entities"]:
            e.update(entity_type="another-type", semantic_brief="changed expected role")
        changed["entities"].reverse()
        for m in changed["memories"]:
            m.update(semantic_brief="changed expected meaning", kind="other")
            if m.get("relation"):
                m["relation"] = {
                    "type": "UNRELATED",
                    "source_entity_key": "ghost",
                    "target_entity_key": "other",
                }
        for q in changed["queries"]:
            q.update(
                semantic_brief="another query contract",
                intent="another-intent",
                temporal_view="other",
            )
        original = build_literal_request(base)
        assert (
            build_literal_request(base.model_copy(update={"input": changed}))
            == original
        )
        encoded = json.dumps(original.model_dump(mode="json"))
        for hidden in (
            control.case_id,
            control.family,
            control.pair_id,
            "semantic_brief",
            "entity_type",
            "relation_meanings",
            "review_nonce",
            "allowed_issue_keys",
            "HELD_BY",
            "WORKS_AT",
            "ISSUED_BY",
        ):
            assert hidden not in encoded
        for e in base.input["entities"]:
            assert e["surface_key"] not in json.dumps(original.input)


@pytest.mark.parametrize(
    "family",
    [
        "relation_direction",
        "passive_and_active_custody",
        "fronted_workplace_roles",
        "independent_content_edge_roles",
        "edge_content_meaning",
    ],
)
def test_host_compares_frozen_literal_roles_even_when_contract_model_flags_nothing(
    family: str,
) -> None:
    control = next(
        c for c in build_controls() if c.family == family and not c.acceptable
    )
    base = build_baseline_request(control)
    reading = validate_literal_reading(
        build_literal_request(base), literal_fixture(control)
    )
    request = build_contract_request(base, reading)
    review, effective = validate_contract_review(
        request, contract_fixture(control, issues=False)
    )
    assert review.issues == []
    assert v2.v1.score_review(control, effective)["correct"]
    assert effective[0]["sources"] == ["host_frozen_literal_comparison"]
    assert request.input["literal_reading"] == reading.model_dump(mode="json")


def test_valid_passive_and_permitted_confirmation_have_no_host_flags() -> None:
    for family in (
        "passive_and_active_custody",
        "fronted_workplace_roles",
        "permitted_confirmation_contract",
    ):
        c = next(c for c in build_controls() if c.family == family and c.acceptable)
        base = build_baseline_request(c)
        reading = validate_literal_reading(
            build_literal_request(base), literal_fixture(c)
        )
        _, effective = validate_contract_review(
            build_contract_request(base, reading), contract_fixture(c)
        )
        assert effective == []


@pytest.mark.parametrize(
    "fault",
    [
        "coverage",
        "duplicate",
        "field_quote",
        "action_quote",
        "role_quote",
        "role_ref",
        "ref_name",
        "temporal_quote",
        "uncertain",
        "memory_mode",
    ],
)
def test_first_pass_invalid_observations_block_second_pass(fault: str) -> None:
    c = build_controls()[15]
    base = build_baseline_request(c)
    raw = literal_fixture(c)
    s = raw["surfaces"][0]
    f = s["frames"][0]
    if fault == "coverage":
        raw["surfaces"].pop()
    elif fault == "duplicate":
        raw["surfaces"].append(deepcopy(s))
    elif fault == "field_quote":
        s["quote"] = "江橙"
    elif fault == "action_quote":
        f["action_quote"] = "杜撰动作"
    elif fault == "role_quote":
        f["actor"]["quote"] = "杜撰角色"
    elif fault == "role_ref":
        f["actor"]["ref"] = "ghost"
    elif fault == "ref_name":
        f["actor"]["ref"] = f["affected"]["ref"]
    elif fault == "temporal_quote":
        f["temporal_quote"] = "杜撰时间"
    elif fault == "uncertain":
        s["status"] = "uncertain"
    else:
        s["query_mode"] = "neutral"
    with pytest.raises(ValueError):
        validate_literal_reading(build_literal_request(base), raw)


@pytest.mark.parametrize(
    "fault",
    [
        "reading_hash",
        "aliases",
        "missing_requirement",
        "rewrite_roles",
        "query_contract",
        "unsupported_adapter",
        "unresolved_reference",
    ],
)
def test_second_pass_cannot_overwrite_reading_or_waive_missing_evidence(
    fault: str,
) -> None:
    c = build_controls()[1] if fault == "query_contract" else build_controls()[14]
    base = build_baseline_request(c)
    raw_reading = literal_fixture(c)
    if fault == "unresolved_reference":
        raw_reading["surfaces"][0]["frames"][0]["actor"]["ref"] = ""
    reading = validate_literal_reading(build_literal_request(base), raw_reading)
    request = build_contract_request(base, reading)
    raw = contract_fixture(c)
    if fault == "reading_hash":
        request.input["literal_reading_sha256"] = "forged"
    elif fault == "aliases":
        request.input["literal_entity_aliases"] = {}
    elif fault == "missing_requirement":
        raw["issues"][0]["citations"].pop()
    elif fault == "rewrite_roles":
        raw["relation_observations"] = []
    elif fault == "query_contract":
        raw["query_contracts"] = []
    elif fault == "unsupported_adapter":
        request.input["memories"][0]["relation"]["type"] = "UNSUPPORTED"
    with pytest.raises(ValueError):
        validate_contract_review(request, raw)


def test_separation_and_valid_quotes_do_not_guarantee_semantic_truth_or_remove_false_flags() -> (
    None
):
    bad = build_controls()[14]
    base = build_baseline_request(bad)
    raw = literal_fixture(bad)
    for surface in raw["surfaces"]:
        frame = surface["frames"][0]
        frame["actor"], frame["affected"] = frame["affected"], frame["actor"]
    reading = validate_literal_reading(build_literal_request(base), raw)
    _, effective = validate_contract_review(
        build_contract_request(base, reading), contract_fixture(bad, issues=False)
    )
    assert v2.v1.score_review(bad, effective)[
        "missed_defect"
    ]  # A wrong literal interpretation can still fool the host.
    good = build_controls()[16]
    base = build_baseline_request(good)
    reading = validate_literal_reading(
        build_literal_request(base), literal_fixture(good)
    )
    raw = contract_fixture(good)
    m = good.reviewer_input["memories"][0]
    raw["issues"] = [
        {
            "surface_key": m["surface_key"],
            "issue_code": "semantic_drift",
            "detail": "离线预置错误结论。",
            "citations": [
                {
                    "surface_key": m["surface_key"],
                    "field": "authored_content",
                    "quote": m["authored_content"],
                },
                {
                    "surface_key": m["surface_key"],
                    "field": "semantic_brief",
                    "quote": m["semantic_brief"],
                },
            ],
        }
    ]
    _, effective = validate_contract_review(build_contract_request(base, reading), raw)
    assert v2.v1.score_review(good, effective)["false_positive"]


class FakeProvider(V2FakeProvider):
    async def generate(self, request: Any) -> dict[str, Any]:
        if self.observer:
            self.observer(
                {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130}
            )
        controls = build_controls()
        if request.output_schema["title"] == "LiteralReading":
            c = next(
                c
                for c in controls
                if build_literal_request(build_baseline_request(c)).input
                == request.input
            )
            return literal_fixture(c)
        c = next(
            c
            for c in controls
            if build_baseline_request(c).input["review_nonce"]
            == request.input["review_nonce"]
        )
        return contract_fixture(c)


async def reference_fixture(
    tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str]:
    v1_ref = await make_reference(tmp, monkeypatch)
    monkeypatch.setattr(v2, "OpenAICompatibleStructuredOutputModel", V2FakeProvider)
    assert await v2.run(v2_args(tmp, v1_ref, 36)) == 0
    p = tmp / "v2.json"
    return p, tmp / "v2-cache", runner.v2.acquire._sha256(p)


def args_for(
    tmp: Path, ref: tuple[Path, Path, str], calls: int, live: bool = True
) -> Any:
    values = [
        "--max-new-calls",
        str(calls),
        "--reference-report",
        str(ref[0]),
        "--reference-cache",
        str(ref[1]),
        "--reference-sha256",
        ref[2],
        "--cache-dir",
        str(tmp / "v3-cache"),
        "--output",
        str(tmp / "v3.json"),
        "--progress-output",
        str(tmp / "v3-progress.json"),
    ]
    if live:
        values.append("--live")
    return runner.parser().parse_args(values)


@pytest.mark.asyncio
async def test_two_stage_budget_stop_resume_and_reference_preservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await reference_fixture(tmp_path, monkeypatch)
    before = {p: runner.v2.acquire._sha256(p) for p in tmp_path.rglob("*.json")}
    monkeypatch.setattr(v2, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    assert await runner.run(args_for(tmp_path, ref, 1)) == 2  # Stop BETWEEN two phases.
    partial = json.loads((tmp_path / "v3-progress.json").read_text("utf-8"))
    assert partial["provider_calls_cumulative"] == 1 and partial["reviewed_count"] == 0
    assert await runner.run(args_for(tmp_path, ref, 71)) == 0
    report = json.loads((tmp_path / "v3.json").read_text("utf-8"))
    assert (
        report["provider_calls_cumulative"] == 72
        and report["usage_cumulative"]["total_tokens"] == 9360
    )
    assert (
        report["gate"]["ok"] and not report["gate"]["blind_corpus_acceptance_granted"]
    )
    assert (
        report["manual_review_queue"] == []
        and report["cohorts"]["opened_v2"]["control_count"] == 36
    )
    assert report["reference"]["raw_response_count"] == 36
    for p, digest in before.items():
        assert runner.v2.acquire._sha256(p) == digest
    monkeypatch.delenv("DOPPEL_API_KEY")
    args = args_for(tmp_path, ref, 0)
    args.output = tmp_path / "v3-replay.json"
    assert await runner.run(args) == 0
    replay = json.loads(args.output.read_text("utf-8"))
    assert (
        replay["last_invocation"]["provider_calls"] == 0
        and replay["last_invocation"]["cache_hits"] == 72
    )
    assert replay["usage_cumulative"] == report["usage_cumulative"]
    for p in tmp_path.rglob("*.json"):
        assert "fake-only-key" not in p.read_text("utf-8")


@pytest.mark.asyncio
async def test_uncertain_first_pass_records_failure_queue_without_second_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await reference_fixture(tmp_path, monkeypatch)

    class Uncertain(FakeProvider):
        async def generate(self, request: Any) -> dict[str, Any]:
            assert request.output_schema["title"] == "LiteralReading"
            raw = await super().generate(request)
            raw["surfaces"][0]["status"] = "uncertain"
            return raw

    monkeypatch.setattr(v2, "OpenAICompatibleStructuredOutputModel", Uncertain)
    assert await runner.run(args_for(tmp_path, ref, 36)) == 1
    report = json.loads((tmp_path / "v3.json").read_text("utf-8"))
    assert report["error_count"] == 36 and len(report["manual_review_queue"]) == 36
    assert report["provider_calls_cumulative"] == 36 and not report["gate"]["ok"]
    assert {r["reason"] for r in report["manual_review_queue"]} == {
        "LiteralReadingValidationError"
    }


@pytest.mark.asyncio
async def test_corrupt_first_phase_cache_not_replaced_or_waived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await reference_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(v2, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    assert await runner.run(args_for(tmp_path, ref, 72)) == 0
    cache = tmp_path / "v3-cache"
    file = next(
        p
        for p in cache.glob("provider-output-v*/*/*.json")
        if "surfaces" in json.loads(p.read_text("utf-8"))["output"]
    )
    file.write_text("{}", "utf-8")
    args = args_for(tmp_path, ref, 72)
    args.output = tmp_path / "corruption-diagnostic.json"
    assert await runner.run(args) == 1
    report = json.loads(args.output.read_text("utf-8"))
    assert report["last_invocation"]["provider_calls"] == 0
    assert report["last_invocation"]["invalid_cache_entries"] == 1
    assert len(report["manual_review_queue"]) == 1 and not report["gate"]["ok"]
    assert file.read_text("utf-8") == "{}"


@pytest.mark.asyncio
async def test_corrupt_v2_reference_stops_before_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await reference_fixture(tmp_path, monkeypatch)
    file = next(ref[1].glob("provider-output-v*/*/*.json"))
    file.write_text("{}", "utf-8")

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("provider accessed before reference validation")

    monkeypatch.setattr(v2, "OpenAICompatibleStructuredOutputModel", forbidden)
    with pytest.raises(v2.ParentCacheIntegrityError):
        await runner.run(args_for(tmp_path, ref, 72))
    assert not (tmp_path / "v3-cache").exists()


@pytest.mark.asyncio
async def test_dry_run_has_no_provider_reference_or_key_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("provider accessed")

    monkeypatch.setattr(v2, "OpenAICompatibleStructuredOutputModel", forbidden)
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    assert (
        await runner.run(
            args_for(
                tmp_path,
                (tmp_path / "absent", tmp_path / "absent-cache", "unused"),
                72,
                False,
            )
        )
        == 0
    )
    assert not list(tmp_path.iterdir())
