"""Versioned quality-suite manifests and publication-readiness gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.memory_quality import (
    MemoryQualityDataset,
    build_metamorphic_memory_quality_dataset,
    load_memory_quality_dataset,
)

DEFAULT_SUITE = Path(__file__).parent / "datasets" / "memory-quality-suite-zh-v2.json"
QualityPartition = Literal["dev", "heldout", "adversarial"]


class QualitySuiteMember(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    partition: QualityPartition
    dataset: str = Field(min_length=1)
    frozen: bool = False


class QualityMetamorphicVariant(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    source_member_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    replacements: dict[str, str] = Field(min_length=1)


class QualitySuiteRequirements(BaseModel):
    model_config = ConfigDict(frozen=True)

    required_partitions: tuple[QualityPartition, ...] = Field(
        default=("dev", "heldout", "adversarial"), min_length=1
    )
    min_case_count: int = Field(default=150, ge=1)
    min_message_count: int = Field(default=1_500, ge=1)
    min_query_count: int = Field(default=150, ge=1)
    min_user_count: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _validate_partitions(self) -> QualitySuiteRequirements:
        if len(self.required_partitions) != len(set(self.required_partitions)):
            raise ValueError("required quality suite partitions must be unique")
        return self


class MemoryQualitySuiteManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite_version: Literal[2] = 2
    name: str = Field(min_length=1)
    language: str = "zh-CN"
    status: Literal["draft", "frozen"] = "draft"
    members: list[QualitySuiteMember] = Field(min_length=1)
    metamorphic_variants: list[QualityMetamorphicVariant] = Field(default_factory=list)
    requirements: QualitySuiteRequirements = Field(
        default_factory=QualitySuiteRequirements
    )

    @model_validator(mode="after")
    def _validate_references(self) -> MemoryQualitySuiteManifest:
        member_ids = [member.member_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("quality suite member IDs must be unique")
        datasets = [member.dataset for member in self.members]
        if len(datasets) != len(set(datasets)):
            raise ValueError("quality suite dataset paths must be unique")
        variant_ids = [variant.variant_id for variant in self.metamorphic_variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("quality suite metamorphic variant IDs must be unique")
        known_members = set(member_ids)
        for variant in self.metamorphic_variants:
            if variant.source_member_id not in known_members:
                raise ValueError(
                    f"unknown metamorphic source member: {variant.source_member_id}"
                )
        return self


@dataclass(frozen=True, slots=True)
class LoadedQualitySuiteMember:
    config: QualitySuiteMember
    dataset: MemoryQualityDataset


@dataclass(frozen=True, slots=True)
class LoadedMemoryQualitySuite:
    manifest: MemoryQualitySuiteManifest
    members: tuple[LoadedQualitySuiteMember, ...]
    variants: tuple[MemoryQualityDataset, ...]
    fingerprint: str

    def audit(self) -> dict[str, Any]:
        partitions = {
            partition: sum(
                member.config.partition == partition for member in self.members
            )
            for partition in ("dev", "heldout", "adversarial")
        }
        case_count = sum(len(member.dataset.cases) for member in self.members)
        message_count = sum(
            len(case.messages)
            for member in self.members
            for case in member.dataset.cases
        )
        query_count = sum(
            len(case.queries)
            for member in self.members
            for case in member.dataset.cases
        )
        user_count = len(
            {
                scope.user_id
                for member in self.members
                for scope in member.dataset.scopes
            }
        )
        requirements = self.manifest.requirements
        errors: list[str] = []
        missing_partitions = sorted(
            partition
            for partition in requirements.required_partitions
            if partitions[partition] == 0
        )
        if missing_partitions:
            errors.append(f"missing required partitions: {missing_partitions}")
        for label, actual, required in (
            ("cases", case_count, requirements.min_case_count),
            ("messages", message_count, requirements.min_message_count),
            ("queries", query_count, requirements.min_query_count),
            ("users", user_count, requirements.min_user_count),
        ):
            if actual < required:
                errors.append(f"{label}: {actual} < required {required}")
        if self.manifest.status != "frozen":
            errors.append("suite status is draft")
        unfrozen_evaluation_members = sorted(
            member.config.member_id
            for member in self.members
            if member.config.partition in {"heldout", "adversarial"}
            and not member.config.frozen
        )
        if unfrozen_evaluation_members:
            errors.append(
                "heldout/adversarial members are not frozen: "
                f"{unfrozen_evaluation_members}"
            )
        return {
            "suite_version": self.manifest.suite_version,
            "name": self.manifest.name,
            "status": self.manifest.status,
            "fingerprint": self.fingerprint,
            "partitions": partitions,
            "counts": {
                "cases": case_count,
                "messages": message_count,
                "queries": query_count,
                "users": user_count,
                "metamorphic_variants": len(self.variants),
            },
            "requirements": requirements.model_dump(mode="json"),
            "publication_ready": not errors,
            "errors": errors,
        }


def load_memory_quality_suite(
    path: str | Path = DEFAULT_SUITE,
) -> LoadedMemoryQualitySuite:
    manifest_path = Path(path).resolve()
    with manifest_path.open(encoding="utf-8") as source:
        manifest = MemoryQualitySuiteManifest.model_validate(json.load(source))

    root = manifest_path.parent
    loaded_members: list[LoadedQualitySuiteMember] = []
    by_id: dict[str, MemoryQualityDataset] = {}
    for member in manifest.members:
        dataset_path = _resolve_suite_dataset(root, member.dataset)
        dataset = load_memory_quality_dataset(dataset_path)
        loaded_members.append(LoadedQualitySuiteMember(member, dataset))
        by_id[member.member_id] = dataset

    variants = tuple(
        build_metamorphic_memory_quality_dataset(
            by_id[variant.source_member_id],
            variant.replacements,
            variant=variant.variant_id,
        )
        for variant in manifest.metamorphic_variants
    )
    fingerprint_payload = {
        "manifest": manifest.model_dump(mode="json"),
        "datasets": {
            member.config.member_id: member.dataset.fingerprint
            for member in loaded_members
        },
        "variants": [dataset.fingerprint for dataset in variants],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return LoadedMemoryQualitySuite(
        manifest=manifest,
        members=tuple(loaded_members),
        variants=variants,
        fingerprint=fingerprint,
    )


def _resolve_suite_dataset(root: Path, configured: str) -> Path:
    relative = Path(configured)
    if relative.is_absolute():
        raise ValueError("quality suite dataset path must be relative")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("quality suite dataset path escapes the suite directory")
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--output")
    parser.add_argument(
        "--require-publication-ready",
        action="store_true",
        help="Exit non-zero while the suite is draft or below its declared gates.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = load_memory_quality_suite(args.suite).audit()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"memory quality suite audit: {output}")
    else:
        sys.stdout.write(rendered)
    if args.require_publication_ready and not report["publication_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
