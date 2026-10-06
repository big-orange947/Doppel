"""Freeze a bounded, offline repair inventory before opening blind retrieval.

This is corpus curation, not a production retrieval rule or an acceptance policy.
No provider, compiler, retrieval engine, or calibration runner is invoked here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarks import evidence_rich_blind_compile as compiler
from benchmarks import evidence_rich_blind_revision_v3 as source
from benchmarks.evidence_rich_blind_authoring import (
    BlindCorpusAuthoringManifest,
    split_owner_authoring_batches,
)

AUTHORED_SHA256 = "d000d2a4ec413a45700b848074e3ec91a2f5f7b0dc043a94f6eeb4394823609e"
REVIEW_SHA256 = "e413f3880d639f52a370e67b707c23092deb438de920a7a23ee6c03ac7c58d3d"
MANIFEST_SHA256 = "70fcb5c2fcbe3b2da7ec89e889b78066394a46027ab27e354ade7e1e3dcf0000"
OUTPUT = source.DATA / "evidence-rich-blind-v1-repair-inventory.json"

# Exact identities from the previously published diagnostic audit. These are
# assistant diagnoses, NOT human approvals, waivers, or machine review results.
DIAGNOSES = {
    ("05", "memory-temporary-residence", "temporal_mismatch"): "ambiguity",
    ("06", "query-no-answer", "answer_leak"): "suspected_false_positive",
    ("08", "memory-competing-first", "relation_mismatch"): "coherence_defect",
    ("08", "memory-stale-route", "relation_mismatch"): "ambiguity",
    ("09", "memory-temporary-residence", "temporal_mismatch"): "ambiguity",
    ("11", "query-subject-correction", "answer_leak"): "suspected_false_positive",
    ("11", "query-no-answer", "answer_leak"): "suspected_false_positive",
    ("12", "query-subject-correction", "answer_leak"): "suspected_false_positive",
    ("12", "query-no-answer", "answer_leak"): "suspected_false_positive",
    ("14", "query-no-answer", "answer_leak"): "suspected_false_positive",
    ("16", "memory-temporary-residence", "temporal_mismatch"): "ambiguity",
    ("18", "memory-competing-first", "relation_mismatch"): "coherence_defect",
    ("18", "memory-stale-route", "relation_mismatch"): "coherence_defect",
    ("18", "query-no-answer", "answer_leak"): "suspected_false_positive",
    ("22", "query-subject-correction", "answer_leak"): "suspected_false_positive",
    ("22", "query-no-answer", "answer_leak"): "suspected_false_positive",
    ("24", "memory-one-hop", "relation_mismatch"): "coherence_defect",
    ("24", "memory-competing-first", "relation_mismatch"): "coherence_defect",
    ("24", "memory-two-hop-first", "relation_mismatch"): "ambiguity",
    ("24", "memory-stale-route", "relation_mismatch"): "ambiguity",
    ("24", "memory-no-answer-related", "relation_mismatch"): "suspected_false_positive",
    ("24", "memory-no-answer-stale", "relation_mismatch"): "suspected_false_positive",
    ("24", "query-no-answer", "answer_leak"): "suspected_false_positive",
}


def authority_fingerprint(manifest: BlindCorpusAuthoringManifest) -> str:
    """Bind every owner identity/label/route/time/type, excluding wording briefs."""
    owners = [owner.model_dump(mode="json") for owner in manifest.owners]
    for owner in owners:
        for field in ("entities", "memories", "queries"):
            for slot in owner[field]:
                del slot["semantic_brief"]
    return compiler._fingerprint(owners)


def build_inventory(
    manifest: BlindCorpusAuthoringManifest,
    authored: dict[str, Any],
    review: dict[str, Any],
    *,
    authored_sha256: str,
    review_sha256: str,
) -> dict[str, Any]:
    """Inspect original surfaces; never modify them or grant corpus acceptance."""
    compiler._validate_authored(manifest, authored)
    if (
        review.get("manifest_fingerprint") != manifest.fingerprint
        or review.get("authored_surfaces_sha256") != authored_sha256
        or review.get("status") != "reviewed_rejected"
        or review.get("accepted") is not False
        or review.get("review_complete") is not True
        or review.get("retrieval_opened") is not False
        or review.get("quality_metrics_available") is not False
        or review.get("auto_rewrite_performed") is not False
    ):
        raise ValueError("inventory requires the bound, unopened rejected review")
    batches = {
        batch.batch_id: batch
        for owner in manifest.owners
        for batch in split_owner_authoring_batches(owner)
    }
    reports = review["batches"]
    if (
        len(reports) != len(batches)
        or {item["batch_id"] for item in reports} != set(batches)
        or review.get("batch_count") != len(batches)
    ):
        raise ValueError("review batch coverage mismatch")
    findings = []
    seen = set()
    for report in reports:
        batch = batches[report["batch_id"]]
        keys = sorted(
            slot.surface_key
            for slot in [*batch.entities, *batch.memories, *batch.queries]
        )
        if (
            report["owner_key"] != batch.owner_key
            or report["reviewed_surface_count"] != len(keys)
            or report["reviewed_surface_keys_sha256"] != compiler._fingerprint(keys)
            or report["issue_count"] != len(report["issues"])
        ):
            raise ValueError("review surface coverage mismatch")
        for issue in report["issues"]:
            identity = (batch.owner_key[-2:], issue["surface_key"], issue["issue_code"])
            if issue["surface_key"] not in keys or identity in seen:
                raise ValueError("unknown or duplicate finding")
            seen.add(identity)
            findings.append(
                {
                    "owner_key": batch.owner_key,
                    **issue,
                    "diagnosis": DIAGNOSES.get(identity, "unresolved"),
                    "decision": "pending_adjudication",
                }
            )
    if seen != set(DIAGNOSES) or review.get("issue_count") != len(findings):
        raise ValueError("findings differ from the frozen diagnostic audit")

    surfaces = {item["owner_key"]: item for item in authored["owners"]}
    work = []
    for owner in manifest.owners:
        item = surfaces[owner.owner_key]
        # All owners, not just the three flagged ones; same original timestamps.
        selected: dict[str, set[str]] = {
            "memory-temporary-residence": {"exact_half_open_residency"},
            "query-temporary-as-of": {"exact_as_of_date"},
        }
        issuance_entities = set()
        if any(memory.relation_type == "ISSUED_BY" for memory in owner.memories):
            issuance_entities = {
                "entity-one-hop-anchor",
                "entity-two-hop-anchor",
                "entity-two-hop-middle",
                "entity-branch-target",
            }
            for key in issuance_entities:
                selected.setdefault(key, set()).add("document_subtype_and_issuer_role")
        if any(memory.relation_type == "ADOPTED_FROM" for memory in owner.memories):
            for key in (
                "memory-one-hop",
                "memory-competing-first",
                "memory-two-hop-first",
                "memory-stale-route",
            ):
                selected.setdefault(key, set()).add(
                    "acquisition_actor_and_transfer_chain"
                )
        renamed_names = {
            item["entity_names_by_id"][entity.entity_id]
            for entity in owner.entities
            if entity.surface_key in issuance_entities
        }
        # Dependency closure includes textual references in distractors, not just
        # graph endpoints. Exact structural references also catch omitted names.
        for memory in owner.memories:
            text = item["memory_content_by_id"][memory.memory_id]
            edge = item["edge_fact_by_memory_id"][memory.memory_id]
            if {
                memory.source_entity_key,
                memory.target_entity_key,
            } & issuance_entities or any(
                name in text or name in edge for name in renamed_names
            ):
                selected.setdefault(memory.surface_key, set()).add(
                    "entity_reference_consistency"
                )
        for query in owner.queries:
            text = item["query_text_by_case_id"][query.case_id]
            if set(query.entity_mentions) & issuance_entities or any(
                name in text for name in renamed_names
            ):
                selected.setdefault(query.surface_key, set()).add(
                    "entity_reference_consistency"
                )

        slots = []
        for field, id_field, mapping in (
            ("entities", "entity_id", "entity_names_by_id"),
            ("memories", "memory_id", "memory_content_by_id"),
            ("queries", "case_id", "query_text_by_case_id"),
        ):
            for slot in getattr(owner, field):
                if slot.surface_key not in selected:
                    continue
                identifier = getattr(slot, id_field)
                slots.append(
                    {
                        "surface_key": slot.surface_key,
                        "surface_kind": field,
                        "reasons": sorted(selected[slot.surface_key]),
                        "original_text": item[mapping][identifier],
                        "original_edge_fact": (
                            item["edge_fact_by_memory_id"][identifier]
                            if field == "memories"
                            else ""
                        ),
                        "original_brief": slot.semantic_brief,
                        "status": "pending_bounded_repair_or_verified_retention",
                    }
                )
        work.append({"owner_key": owner.owner_key, "slots": slots})
    counts = Counter(
        reason for row in work for slot in row["slots"] for reason in slot["reasons"]
    )
    return {
        "runner": "doppel.evidence-rich-blind-repair-inventory.v1",
        "status": "inventory_frozen_repair_pending",
        "source": {
            "authored_sha256": authored_sha256,
            "review_sha256": review_sha256,
            "manifest_fingerprint": manifest.fingerprint,
            "authority_fingerprint": authority_fingerprint(manifest),
        },
        "constraints": {
            "unchanged_private_authority_and_gold": True,
            "unlisted_surfaces_must_remain_byte_identical": True,
            "listed_surfaces_are_not_required_to_change": True,
            "original_reports_and_caches_immutable": True,
            "selection_by_retrieval_results_forbidden": True,
            "residency_interval": "[2026-02-01,2026-04-01)",
            "residency_query_date": "2026-03-15",
            "query_unknown_answer_hints_forbidden": True,
        },
        "findings": findings,
        "owners": work,
        "summary": {
            "reported_findings": len(findings),
            "diagnoses": dict(Counter(row["diagnosis"] for row in findings)),
            "owner_count": len(work),
            "candidate_surface_slots": sum(len(row["slots"]) for row in work),
            "reason_slot_counts": dict(sorted(counts.items())),
        },
        "gate": {
            "corpus_acceptance_granted": False,
            "compilation_allowed": False,
            "retrieval_opened": False,
            "quality_metrics_available": False,
            "publication_ready": False,
        },
        "usage": {"provider_calls": 0, "tokens": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    manifest = source.build_manifest()
    if manifest.fingerprint != MANIFEST_SHA256:
        raise ValueError("host manifest changed since diagnostic audit")
    inputs = []
    for path, expected in (
        (source.AUTHORED, AUTHORED_SHA256),
        (source.REVIEW, REVIEW_SHA256),
    ):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"source hash mismatch: {path.name}")
        inputs.append(json.loads(raw))
    report = build_inventory(
        manifest,
        inputs[0],
        inputs[1],
        authored_sha256=AUTHORED_SHA256,
        review_sha256=REVIEW_SHA256,
    )
    # Exclusive creation preserves previous inventories and every parent artifact.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"output: {args.output}")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
