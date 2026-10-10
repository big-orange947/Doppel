"""Regrade frozen opened answers with the content-pinned LongMemEval protocol.

No Reader, retrieval, graph, source ingestion or core-default changes. API keys
are environment-only. Missing credentials never trigger another model fallback.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import StructuredOutputProviderError

RUNNER = "doppel.public-memory-official-regrade.v1"
MODEL = "gpt-4o-2024-08-06"
BASE_URL = "https://api.openai.com/v1"
UPSTREAM = Path(__file__).parent / "upstream/longmemeval/evaluate_qa.py.txt"
UPSTREAM_SHA256 = "ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251"
ANSWERS_SHA256 = "0545aec92c8febd1cc55e6d4ce76714b8f634c9dee0242eae326766119295c33"
COHORT = (
    "d52b4f67",
    "21d02d0d",
    "38146c39",
    "gpt4_d9af6064",
    "3ba21379",
    "ceb54acb",
    "29f2956b_abs",
)
PROFILES = ("s-raw-vector-reranked", "full-oracle-no-retrieval")
POLICIES = ("reader_v2", "grounded_advice_v1")


def official_prompt(task, question, answer, response, abstention=False):
    text = UPSTREAM.read_text(encoding="utf-8")  # universal newline normalization
    if hashlib.sha256(text.encode()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("upstream snapshot changed")
    nodes: list[ast.stmt] = [
        n
        for n in ast.parse(text).body
        if isinstance(n, ast.FunctionDef) and n.name == "get_anscheck_prompt"
    ]
    if len(nodes) != 1:
        raise ValueError("upstream prompt function missing or duplicated")
    namespace: dict[str, Any] = {}
    # Only this hash-bound function, never upstream imports/CLI/backoff/network.
    exec(  # noqa: S102 - execute only the pinned upstream prompt function
        compile(ast.Module(body=nodes, type_ignores=[]), str(UPSTREAM), "exec"),
        namespace,
    )
    return namespace["get_anscheck_prompt"](
        task, question, answer, response, abstention
    )


def validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in base_url)
        or parsed.path.rstrip("/").endswith("/chat/completions")
    ):
        raise ValueError("HTTPS base URL without credentials/query/fragment required")
    return base_url.rstrip("/")


def prepare_rows(parent, source, manifest, bindings):
    payload = dict(parent["plan"])
    fingerprint = payload.pop("plan_fingerprint", None)
    if (
        parent.get("runner") != "doppel.public-memory-response-policy-paired.v1"
        or parent.get("status") != "complete"
        or fingerprint != _hash(payload)
        or parent["plan"]["input_sha256"]["source"] != bindings["source"]
        or parent["plan"]["input_sha256"]["manifest"] != bindings["manifest"]
        or manifest["source_sha256"] != bindings["source"]
        or parent["plan"]["contexts"] != [[c, p] for c in COHORT for p in PROFILES]
        or parent["plan"]["policies"] != list(POLICIES)
    ):
        raise ValueError("complete unchanged parent and source binding required")
    diagnostic = {
        r["case_id"] for r in manifest["cases"] if r["partition"] == "diagnostic"
    }
    if not set(COHORT) <= diagnostic:
        raise ValueError("opened diagnostic cases only")
    refs = {r["question_id"]: r for r in source if r["question_id"] in COHORT}
    if len(refs) != 7 or sum(r["question_id"] in COHORT for r in source) != 7:
        raise ValueError("seven unique references required")
    rows, seen = [], set()
    for row in parent["rows"]:
        identity = (row["case_id"], row["context_profile"], row["policy"])
        if identity in seen or identity[0] not in refs:
            raise ValueError("duplicate or unexpected answer")
        seen.add(identity)
        ref = refs[identity[0]]
        if (
            row["status"] != "complete"
            or row["category"] != ref["question_type"]
            or row["abstention_case"] != ("_abs" in identity[0])
            or not isinstance(row["reader"]["answer"], str)
            or not row["reader"]["answer"].strip()
            or type(row["grade"]["answer_correct"]) is not bool
        ):
            raise ValueError("invalid original answer row")
        prompt = official_prompt(
            ref["question_type"],
            ref["question"],
            ref["answer"],
            row["reader"]["answer"],
            abstention=row["abstention_case"],
        )
        rows.append(
            {
                "identity": list(identity),
                "category": row["category"],
                "abstention_case": row["abstention_case"],
                "hypothesis": row["reader"]["answer"],
                "old_diagnostic_label": row["grade"]["answer_correct"],
                "prompt": prompt,
            }
        )
    if seen != {(c, p, s) for c in COHORT for p in PROFILES for s in POLICIES}:
        raise ValueError("all 28 original rows required; no score-based selection")
    return rows, [
        {k: refs[c][k] for k in ("question_id", "question_type", "question", "answer")}
        for c in COHORT
    ]


class OfficialOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    raw_response: str
    returned_model: str
    finish_reason: Literal["stop", "length", "content_filter"]


def request_for(row):
    # This is a LOCAL cache/ledger envelope, not a JSON-mode HTTP request.
    return StructuredGenerationRequest(
        instructions="local receipt only; never transmitted",
        input={"prompt": row["prompt"]},
        output_schema=OfficialOutput.model_json_schema(),
    )


def wire_request(request):
    if set(request.input) != {"prompt"} or not isinstance(request.input["prompt"], str):
        raise ValueError("invalid prompt envelope")
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": request.input["prompt"]}],
        "n": 1,
        "temperature": 0,
        "max_tokens": 10,
    }


class OfficialChatModel:
    """Plain Chat Completions, no SDK retries or schema/prompt embellishment."""

    name = MODEL

    def __init__(self, key, base_url, ledger, *, transport=None):
        self._key = key
        self._base_url = validate_base_url(base_url)
        self._ledger = ledger
        self._transport = transport
        self.version = (
            RUNNER
            + ":"
            + _hash({"base_url": self._base_url, "upstream": UPSTREAM_SHA256})
        )

    async def generate(self, request) -> Mapping[str, Any]:
        if not self._key:
            raise ValueError("OPENAI_API_KEY required; no model fallback")
        try:
            async with (
                httpx.AsyncClient(
                    transport=self._transport,
                    timeout=60,
                    follow_redirects=False,
                ) as client,
                client.stream(
                    "POST",
                    self._base_url + "/chat/completions",
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
                        "official HTTP attempt failed; no retry",
                        status_code=response.status_code,
                        retryable=False,
                    )
                body = bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body) > 100_000:
                        raise ValueError("response exceeded bound")
                if self._key.encode() in body:
                    raise ValueError("credential reflected in response; not persisted")
                data = json.loads(body)
                if self._key in json.dumps(data, ensure_ascii=False):
                    raise ValueError("decoded credential reflection; not persisted")
            # Account a returned usage receipt even if subsequent shape checks fail.
            usage = data.get("usage")
            if isinstance(usage, dict):
                observed = {
                    target: usage[src]
                    for src, target in (
                        ("prompt_tokens", "input_tokens"),
                        ("completion_tokens", "output_tokens"),
                        ("total_tokens", "total_tokens"),
                    )
                    if type(usage.get(src)) is int and usage[src] >= 0
                }
                details = usage.get("prompt_tokens_details")
                if (
                    isinstance(details, dict)
                    and type(details.get("cached_tokens")) is int
                    and details["cached_tokens"] >= 0
                ):
                    observed["cached_input_tokens"] = details["cached_tokens"]
                if observed:
                    self._ledger.observe_usage(observed)
            choices = data["choices"]
            if data["model"] != MODEL or len(choices) != 1:
                raise ValueError("returned model snapshot/choices mismatch")
            output = OfficialOutput(
                raw_response=choices[0]["message"]["content"],
                returned_model=data["model"],
                finish_reason=choices[0]["finish_reason"],
            )
            if not output.raw_response.strip():
                raise ValueError("empty official verdict")
            return output.model_dump(mode="json")
        except StructuredOutputProviderError:
            raise
        except httpx.TimeoutException:
            raise StructuredOutputProviderError(
                "timeout", "official scoring timed out; no retry"
            ) from None
        except httpx.TransportError:
            raise StructuredOutputProviderError(
                "transport_error", "official transport failed; no retry"
            ) from None
        except Exception:  # noqa: BLE001 - never expose key/provider body/headers
            raise StructuredOutputProviderError(
                "invalid_response_shape", "official scoring response invalid; no retry"
            ) from None


def verdict(output):
    text = output.raw_response.strip()
    return {
        **output.model_dump(mode="json"),
        "official_label": "yes"
        in text.lower(),  # exact upstream rule, not an exact-match rewrite
        "strict_yes_no_valid": text.lower() in {"yes", "no"},
        "clean_completion": output.finish_reason == "stop",
    }


def export_inputs(run_dir, rows, references):
    """Four ordinary seven-line upstream-compatible files, original question IDs."""
    files = {
        "references.json": json.dumps(references, ensure_ascii=False, indent=2) + "\n"
    }
    for pi, profile in enumerate(PROFILES):
        for si, policy in enumerate(POLICIES):
            selected = [r for r in rows if r["identity"][1:] == [profile, policy]]
            files[f"hypotheses-context{pi}-policy{si}.jsonl"] = "".join(
                json.dumps(
                    {"question_id": r["identity"][0], "hypothesis": r["hypothesis"]},
                    ensure_ascii=False,
                )
                + "\n"
                for r in selected
            )
    hashes = {}
    for name, text in files.items():
        content = text.encode()
        path = run_dir / "exports" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError("immutable export changed")
        else:
            with path.open("xb") as handle:
                handle.write(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    return hashes


def build_plan(rows, bindings, exports, base_url):
    requests = [request_for(r) for r in rows]
    plan = {
        "runner": RUNNER,
        "input_sha256": bindings,
        "upstream_sha256_lf": UPSTREAM_SHA256,
        "model": MODEL,
        "base_url": validate_base_url(base_url),
        "settings": {"n": 1, "temperature": 0, "max_tokens": 10},
        "row_identities": [r["identity"] for r in rows],
        "request_sha256": [_hash(r.model_dump(mode="json")) for r in requests],
        "wire_sha256": [_hash(wire_request(r)) for r in requests],
        "export_sha256": exports,
        "max_new_calls": 28,
        "failure_policy": "stop and preserve; no automatic retries",
        "parser": "upstream substring yes; strict validity reported separately",
        "source_sha256": {
            str(
                path.resolve().relative_to(Path(__file__).parent.parent)
            ): hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
            for path in (
                Path(__file__),
                Path("benchmarks/public_memory_runtime.py"),
                Path("benchmarks/public_memory_high_config_first.py"),
                Path("benchmarks/relation_planner_quality.py"),
            )
        },
        "opened_cases": 7,
        "correlated_rows": 28,
        "formal_longmemeval_result": False,
        "aml_result": False,
        "readers_regenerated": False,
        "new_graph_calls": 0,
    }
    plan["plan_fingerprint"] = _hash(plan)
    return plan


def summarize(rows):
    result = {}
    for p in PROFILES:
        for s in POLICIES:
            selected = [r for r in rows if r["identity"][1:] == [p, s]]
            arm = {}
            for name, subset in (
                ("all", selected),
                ("ordinary", [r for r in selected if not r["abstention_case"]]),
                ("refusal", [r for r in selected if r["abstention_case"]]),
            ):
                valid = [r for r in subset if r.get("status") == "complete"]
                clean = [
                    r
                    for r in valid
                    if r["grade"]["strict_yes_no_valid"]
                    and r["grade"]["clean_completion"]
                ]
                arm[name] = {
                    "rows_observed": len(subset),
                    "graded": len(valid),
                    "clean_graded": len(clean),
                    "upstream_correct": sum(
                        r["grade"]["official_label"] for r in valid
                    ),
                    "old_label_disagreements": sum(
                        r["grade"]["official_label"] != r["old_diagnostic_label"]
                        for r in valid
                    ),
                }
            result[p + "/" + s] = arm
    return result


async def execute(args, rows, plan, *, transport=None):
    key = "" if args.cache_only else os.environ.get("OPENAI_API_KEY", "")
    if not key and not args.cache_only:
        raise ValueError("OPENAI_API_KEY missing; preflight remains free")
    _bind_json(args.run_dir / "plan.json", plan)
    ledger = DurableCallLedger(
        args.run_dir / "usage.sqlite",
        budget_id=plan["plan_fingerprint"],
        max_calls=28,
        max_request_bytes=100_000,
        max_total_request_bytes=2_800_000,
    )
    model = PilotStructuredModel(
        OfficialChatModel(key, args.base_url, ledger, transport=transport),
        ledger=ledger,
        cache_dir=args.run_dir / "cache",
        cache_only=args.cache_only,
    )
    results, stopped = [], ""
    try:
        for index, row in enumerate(rows):
            item = {k: v for k, v in row.items() if k != "prompt"}
            item["status"] = "failed"
            try:
                raw = await persisted_generation(
                    model,
                    request_for(row),
                    OfficialOutput,
                    args.run_dir / "receipts" / f"row-{index:02d}.json",
                )
                item.update(status="complete", grade=verdict(raw))
                if (
                    not item["grade"]["strict_yes_no_valid"]
                    or not item["grade"]["clean_completion"]
                ):
                    stopped = "invalid_or_truncated_verdict_no_retry"
            except Exception as error:  # noqa: BLE001 - never print provider/key text
                item["failure_type"] = type(error).__name__
                stopped = "preserved_scoring_failure_no_retry"
            results.append(item)
            print(f"row {index + 1}/28: {item['status']}", flush=True)
            if stopped:
                break
        return {
            "status": "complete" if len(results) == 28 and not stopped else "stopped",
            "rows": results,
            "summary": summarize(results),
            "stopped_reason": stopped,
            "usage": model.report(),
        }
    finally:
        ledger.close()


async def run(args):
    paths = {k: getattr(args, k) for k in ("answers", "source", "manifest")}
    contents = {k: p.read_bytes() for k, p in paths.items()}
    bindings = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    if bindings["answers"] != ANSWERS_SHA256:
        raise ValueError("only the frozen 28 original answers may be regraded")
    rows, refs = prepare_rows(
        json.loads(contents["answers"]),
        json.loads(contents["source"]),
        json.loads(contents["manifest"]),
        bindings,
    )
    exports = export_inputs(args.run_dir, rows, refs)
    plan = build_plan(rows, bindings, exports, args.base_url)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "official_scoring_protocol": True,
        "publication_ready": False,
        "formal_longmemeval_result": False,
        "aml_result": False,
        "provider": "openai"
        if args.base_url.rstrip("/") == BASE_URL
        else "compatible_unverified",
        "provider_model_authenticity_independently_verified": False,
        "record_or_index_writes": 0,
        "reader_or_retrieval_calls": 0,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
            != plan
        ):
            raise ValueError("unchanged preregistered preflight required")
        report.update(await execute(args, rows, plan))
    report["execution_metadata"] = execution_metadata()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    defaults = {
        "answers": "data/doppel/public-memory-response-policy-live-v1.json",
        "source": "data/public-benchmarks/longmemeval_s_cleaned.json",
        "manifest": "data/doppel/longmemeval-expansion-50-manifest-v1.json",
        "run-dir": "data/doppel/public-memory-official-regrade-v1",
    }
    for name, default in defaults.items():
        parser.add_argument("--" + name, type=Path, default=Path(default))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve existing outputs; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(json.dumps({"status": report["status"], "rows": 28}))
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
