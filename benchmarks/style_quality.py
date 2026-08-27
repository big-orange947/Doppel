"""Deterministic, repository-only StyleProfessor quality benchmark."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory import (
    Actor,
    ChatMessage,
    DeterministicStyleAnalyzer,
    StyleMinerConfig,
    StyleProfessor,
    StyleProfessorConfig,
    StyleQualityConfig,
    StyleQualityEvaluator,
    __version__,
)
from doppel_memory.models import utc_now

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "style-quality-v1.json"


class StyleQualityCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    messages: list[str]
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_score: float | None = Field(default=None, ge=0.0, le=1.0)
    should_pass: bool


class StyleQualityDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: Literal[1] = 1
    name: str
    min_candidate_messages: int = Field(ge=1)
    passing_score: float = Field(ge=0.0, le=1.0)
    reference_messages: list[str] = Field(min_length=1)
    cases: list[StyleQualityCase] = Field(min_length=1)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()


def load_style_quality_dataset(
    path: str | Path = DEFAULT_DATASET,
) -> StyleQualityDataset:
    with Path(path).open(encoding="utf-8") as source:
        return StyleQualityDataset.model_validate(json.load(source))


async def run_style_quality_benchmark(
    dataset: StyleQualityDataset,
) -> dict[str, Any]:
    analyzer_config = StyleMinerConfig(
        min_messages=1,
        max_common_phrases=0,
    )
    reference_messages = [
        ChatMessage.of(
            Actor.OWNER,
            text,
            "2026-01-01T00:00:00Z",
            event_id=f"reference-{index}",
        )
        for index, text in enumerate(dataset.reference_messages, start=1)
    ]
    profile = await DeterministicStyleAnalyzer().analyze(
        reference_messages, config=analyzer_config
    )
    if profile is None:  # pragma: no cover - guarded by dataset validation/config
        raise RuntimeError("reference dataset did not produce a style profile")

    professor = StyleProfessor(
        StyleProfessorConfig(
            min_reliable_messages=len(reference_messages),
            full_confidence_messages=len(reference_messages),
        )
    )
    guidance = professor.compile(profile)
    evaluator = StyleQualityEvaluator(
        StyleQualityConfig(
            min_candidate_messages=dataset.min_candidate_messages,
            passing_score=dataset.passing_score,
        )
    )
    errors: list[str] = []
    if not guidance.usable or not guidance.prompt or not guidance.directives:
        errors.append("professor did not produce usable bounded guidance")
    if len(guidance.prompt) > professor.config.max_prompt_chars:
        errors.append("professor prompt exceeded its configured character budget")

    case_results: list[dict[str, Any]] = []
    for case in dataset.cases:
        report = evaluator.evaluate(profile, case.messages)
        case_errors: list[str] = []
        if case.min_score is not None and report.aggregate_score < case.min_score:
            case_errors.append(
                f"score {report.aggregate_score:.4f} is below {case.min_score:.4f}"
            )
        if case.max_score is not None and report.aggregate_score > case.max_score:
            case_errors.append(
                f"score {report.aggregate_score:.4f} is above {case.max_score:.4f}"
            )
        if report.passed is not case.should_pass:
            case_errors.append(
                f"passed={report.passed} does not match expected {case.should_pass}"
            )
        errors.extend(f"{case.name}: {error}" for error in case_errors)
        case_results.append(
            {
                "name": case.name,
                "expected_pass": case.should_pass,
                "min_score": case.min_score,
                "max_score": case.max_score,
                "report": report.model_dump(mode="json"),
                "errors": case_errors,
            }
        )

    return {
        "result_schema_version": 1,
        "doppel_version": __version__,
        "generated_at": utc_now().isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.dataset_version,
            "fingerprint": dataset.fingerprint,
            "reference_message_count": len(dataset.reference_messages),
            "case_count": len(dataset.cases),
        },
        "professor": {
            "name": guidance.professor,
            "version": guidance.professor_version,
            "profile_fingerprint": guidance.profile_fingerprint,
            "config_fingerprint": guidance.config_fingerprint,
            "prompt_chars": len(guidance.prompt),
            "directive_count": len(guidance.directives),
            "omitted_features": guidance.omitted_features,
        },
        "cases": case_results,
        "correctness": {"passed": not errors, "errors": errors},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output")
    return parser


async def _main() -> int:
    args = _parser().parse_args()
    result = await run_style_quality_benchmark(load_style_quality_dataset(args.dataset))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if result["correctness"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
