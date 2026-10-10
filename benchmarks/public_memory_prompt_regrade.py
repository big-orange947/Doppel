"""DeepSeek diagnosis using pinned LongMemEval prompts, NOT official scoring.

Regrade existing opened answers only. Separate plan/cache/budget from GPT-4o;
no Reader, retrieval, graph, default migration or question-specific branches.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from benchmarks import public_memory_official_scoring as pinned
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_oracle_diagnostic import balance
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.openai_compatible import StructuredOutputProviderError

RUNNER = "doppel.public-memory-deepseek-prompt-regrade.v1"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
RETURNED_MODELS = ("deepseek-flash", "deepseek-v4-flash", "deepseek-v4.1-flash")


def wire_request(request):
    wire = pinned.wire_request(request)
    wire.update(model=MODEL, thinking={"type": "disabled"})
    # DeepSeek documents one choice, not OpenAI's n parameter; enforce one below.
    wire.pop("n")
    return wire


class DeepSeekPromptJudge:
    name = MODEL
    version = (
        RUNNER
        + ":"
        + _hash(
            {
                "base_url": BASE_URL,
                "upstream": pinned.UPSTREAM_SHA256,
                "thinking": "disabled",
            }
        )
    )

    def __init__(self, key, ledger, *, transport=None):
        self._key, self._ledger, self._transport = key, ledger, transport

    async def generate(self, request) -> Mapping[str, Any]:
        if not self._key:
            raise ValueError("DEEPSEEK_API_KEY required; no fallback")
        try:
            async with (
                httpx.AsyncClient(
                    transport=self._transport, timeout=60, follow_redirects=False
                ) as client,
                client.stream(
                    "POST",
                    BASE_URL + "/chat/completions",
                    headers={"Authorization": "Bearer " + self._key},
                    json=wire_request(request),
                ) as response,
            ):
                if response.status_code != 200:
                    code = {
                        401: "authentication_error",
                        403: "authentication_error",
                        429: "rate_limited",
                    }.get(response.status_code, "http_error")
                    raise StructuredOutputProviderError(
                        code,
                        "diagnostic HTTP failure; no retry",
                        status_code=response.status_code,
                    )
                body = bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body) > 100_000:
                        raise ValueError("response too large")
                if self._key.encode() in body:
                    raise ValueError("reflected credential")
                data = json.loads(body)
                if self._key in json.dumps(data, ensure_ascii=False):
                    raise ValueError("decoded reflected credential")
            usage = data.get("usage")
            if isinstance(usage, dict):
                observed = {
                    target: usage[src]
                    for src, target in (
                        ("prompt_tokens", "input_tokens"),
                        ("completion_tokens", "output_tokens"),
                        ("total_tokens", "total_tokens"),
                        ("prompt_cache_hit_tokens", "cached_input_tokens"),
                        ("prompt_cache_miss_tokens", "cache_miss_input_tokens"),
                    )
                    if type(usage.get(src)) is int and usage[src] >= 0
                }
                details = usage.get("completion_tokens_details")
                if (
                    isinstance(details, dict)
                    and type(details.get("reasoning_tokens")) is int
                    and details["reasoning_tokens"] >= 0
                ):
                    observed["reasoning_tokens"] = details["reasoning_tokens"]
                if observed:
                    self._ledger.observe_usage(observed)
            if data["model"] not in RETURNED_MODELS or len(data["choices"]) != 1:
                raise ValueError("unexpected returned model or choice count")
            choice = data["choices"][0]
            output = pinned.OfficialOutput(
                raw_response=choice["message"]["content"],
                returned_model=data["model"],
                finish_reason=choice["finish_reason"],
            )
            if not output.raw_response.strip():
                raise ValueError("empty verdict")
            return output.model_dump(mode="json")
        except StructuredOutputProviderError:
            raise
        except httpx.TimeoutException:
            raise StructuredOutputProviderError(
                "timeout", "diagnostic timeout; no retry"
            ) from None
        except httpx.TransportError:
            raise StructuredOutputProviderError(
                "transport_error", "diagnostic transport failure; no retry"
            ) from None
        except Exception:  # noqa: BLE001 - no key/body/header/error detail retention
            raise StructuredOutputProviderError(
                "invalid_response_shape", "invalid diagnostic response; no retry"
            ) from None


def verdict(output):
    result = pinned.verdict(output)
    result["upstream_parser_label"] = result.pop("official_label")
    return result


def summarize(rows):
    # Reuse aggregation, not its official-labelled presentation.
    adapted = [
        {
            **r,
            "grade": {
                **r["grade"],
                "official_label": r["grade"]["upstream_parser_label"],
            },
        }
        if "grade" in r
        else r
        for r in rows
    ]
    result = pinned.summarize(adapted)
    for arm in result.values():
        for subset in arm.values():
            subset["prompt_correct"] = subset.pop("upstream_correct")
    return result


def build_plan(rows, bindings, exports):
    plan = pinned.build_plan(rows, bindings, exports, BASE_URL)
    plan.pop("plan_fingerprint")
    plan.update(
        runner=RUNNER,
        model=MODEL,
        settings={"temperature": 0, "max_tokens": 10, "thinking": {"type": "disabled"}},
        wire_sha256=[_hash(wire_request(pinned.request_for(r))) for r in rows],
        accepted_returned_models=list(RETURNED_MODELS),
        official_scoring_protocol=False,
        official_prompt_reused=True,
        same_model_family_reader_and_judge=True,
        model_snapshot_pinned=False,
        balance_stop_cny=1,
        balance_stop_is_post_spend_not_hard_currency_cap=True,
    )
    for path in (Path(__file__), Path("benchmarks/public_memory_oracle_diagnostic.py")):
        plan["source_sha256"][
            str(path.resolve().relative_to(Path(__file__).parent.parent))
        ] = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    plan["plan_fingerprint"] = _hash(plan)
    return plan


async def execute(args, rows, plan, *, transport=None, balance_reader=balance):
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("DEEPSEEK_API_KEY missing; no OpenAI fallback")
    _bind_json(args.run_dir / "plan.json", plan)
    initial = None
    if not args.cache_only:
        try:
            current = await balance_reader(key)
            initial_path = args.run_dir / "balance-start.json"
            if not initial_path.exists():
                save(initial_path, {"initial_cny": current})
            initial = json.loads(initial_path.read_text(encoding="utf-8"))[
                "initial_cny"
            ]
        except Exception:  # noqa: BLE001 - redacted auth/balance failure
            return {
                "status": "stopped",
                "rows": [],
                "summary": summarize([]),
                "stopped_reason": "balance_unavailable_before_scoring",
                "usage": None,
            }
    ledger = DurableCallLedger(
        args.run_dir / "usage.sqlite",
        budget_id=plan["plan_fingerprint"],
        max_calls=28,
        max_request_bytes=100_000,
        max_total_request_bytes=2_800_000,
    )
    model = PilotStructuredModel(
        DeepSeekPromptJudge(key, ledger, transport=transport),
        ledger=ledger,
        cache_dir=args.run_dir / "cache",
        cache_only=args.cache_only,
    )
    results, stopped, final_balance = [], "", None
    try:
        for index, row in enumerate(rows):
            item = {k: v for k, v in row.items() if k != "prompt"}
            item["status"] = "failed"
            try:
                if not args.cache_only:
                    final_balance = await balance_reader(key)
                    if (
                        final_balance <= 0
                        or initial - final_balance >= plan["balance_stop_cny"]
                    ):
                        item["status"] = "budget_stopped"
                        stopped = "observed_balance_stop"
                if not stopped:
                    raw = await persisted_generation(
                        model,
                        pinned.request_for(row),
                        pinned.OfficialOutput,
                        args.run_dir / "receipts" / f"row-{index:02d}.json",
                    )
                    item.update(status="complete", grade=verdict(raw))
                    if (
                        not item["grade"]["strict_yes_no_valid"]
                        or not item["grade"]["clean_completion"]
                    ):
                        stopped = "invalid_or_truncated_verdict_no_retry"
            except Exception as error:  # noqa: BLE001 - no provider/key text
                item["failure_type"] = type(error).__name__
                stopped = "preserved_scoring_or_balance_failure_no_retry"
            results.append(item)
            print(f"row {index + 1}/28: {item['status']}", flush=True)
            if stopped:
                break
        if not args.cache_only:
            try:
                final_balance = await balance_reader(key)
            except Exception:  # noqa: BLE001 - unknown billing stays unknown
                final_balance = None
        return {
            "status": "complete" if len(results) == 28 and not stopped else "stopped",
            "rows": results,
            "summary": summarize(results),
            "stopped_reason": stopped,
            "usage": model.report(),
            "balance_observation": {
                "initial_cny": initial,
                "final_cny": final_balance,
                "delta_cny": None
                if initial is None or final_balance is None
                else initial - final_balance,
                "exclusive_billing_attribution_proven": False,
            },
        }
    finally:
        ledger.close()


async def run(args):
    contents = {
        k: getattr(args, k).read_bytes() for k in ("answers", "source", "manifest")
    }
    bindings = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    if bindings["answers"] != pinned.ANSWERS_SHA256:
        raise ValueError("only frozen original answers may be regraded")
    rows, refs = pinned.prepare_rows(
        json.loads(contents["answers"]),
        json.loads(contents["source"]),
        json.loads(contents["manifest"]),
        bindings,
    )
    plan = build_plan(rows, bindings, pinned.export_inputs(args.run_dir, rows, refs))
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "official_scoring_protocol": False,
        "official_prompt_reused": True,
        "formal_longmemeval_result": False,
        "aml_result": False,
        "publication_ready": False,
        "provider": "deepseek",
        "record_or_index_writes": 0,
        "reader_or_retrieval_calls": 0,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
            != plan
        ):
            raise ValueError("unchanged separate DeepSeek preflight required")
        report.update(await execute(args, rows, plan))
    report["execution_metadata"] = execution_metadata()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in {
        "answers": "data/doppel/public-memory-response-policy-live-v1.json",
        "source": "data/public-benchmarks/longmemeval_s_cleaned.json",
        "manifest": "data/doppel/longmemeval-expansion-50-manifest-v1.json",
        "run-dir": "data/doppel/public-memory-deepseek-prompt-regrade-v1",
    }.items():
        parser.add_argument("--" + name, type=Path, default=Path(default))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve old outputs; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "rows": len(report.get("rows", [])),
                "summary": report.get("summary", {}),
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
