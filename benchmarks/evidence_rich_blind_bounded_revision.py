"""Apply a local corpus-curation recipe within the frozen blind repair inventory.

This module does not tune retrieval, invoke a provider, adjudicate review findings,
or grant acceptance. Original artifacts remain immutable. Recipes containing blind
surface text stay local alongside the resulting before/after diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from benchmarks import evidence_rich_blind_repair_inventory as inventory
from benchmarks.evidence_rich_blind_authoring import BlindCorpusAuthoringManifest

DATA = inventory.source.DATA
RECIPE = DATA / "evidence-rich-blind-v1-bounded-repair-recipe.json"
PREFIX = DATA / "evidence-rich-blind-v1-bounded-revised"
INVENTORY_SHA256 = "049ec372ff6106fa79c9c415f7ffd59a2f1edb13f8ccee7d15e68327a4bd0e27"
FIELDS = (
    ("entities", "entity_id", "entity_names_by_id"),
    ("memories", "memory_id", "memory_content_by_id"),
    ("queries", "case_id", "query_text_by_case_id"),
)


def _replace_names(text: str, replacements: dict[str, str]) -> str:
    """One pass, longest match first: replacement text is never re-replaced."""
    if not replacements:
        return text
    pattern = "|".join(
        re.escape(name) for name in sorted(replacements, key=len, reverse=True)
    )
    return re.sub(pattern, lambda match: replacements[match.group()], text)


def validate_revision(
    before_manifest: BlindCorpusAuthoringManifest,
    after_manifest: BlindCorpusAuthoringManifest,
    before: dict[str, Any],
    after: dict[str, Any],
    frozen: dict[str, Any],
) -> list[dict[str, Any]]:
    """Enforce private authority and the exact slot-level repair boundary."""
    if inventory.authority_fingerprint(
        before_manifest
    ) != inventory.authority_fingerprint(after_manifest) or frozen["source"][
        "authority_fingerprint"
    ] != inventory.authority_fingerprint(before_manifest):
        raise ValueError("private authority or gold changed")
    if frozen["source"]["manifest_fingerprint"] != before_manifest.fingerprint:
        raise ValueError("inventory manifest binding mismatch")
    inventory.compiler._validate_authored(after_manifest, after)
    allowed = {
        (owner["owner_key"], slot["surface_key"])
        for owner in frozen["owners"]
        for slot in owner["slots"]
    }
    original = {owner["owner_key"]: owner for owner in before["owners"]}
    revised = {owner["owner_key"]: owner for owner in after["owners"]}
    after_owners = {owner.owner_key: owner for owner in after_manifest.owners}
    changes = []
    for owner in before_manifest.owners:
        for field, id_field, mapping in FIELDS:
            new_slots = {
                slot.surface_key: slot
                for slot in getattr(after_owners[owner.owner_key], field)
            }
            for slot in getattr(owner, field):
                identifier = getattr(slot, id_field)
                values = {
                    "text": (
                        original[owner.owner_key][mapping][identifier],
                        revised[owner.owner_key][mapping][identifier],
                    ),
                    "semantic_brief": (
                        slot.semantic_brief,
                        new_slots[slot.surface_key].semantic_brief,
                    ),
                }
                if field == "memories":
                    values["edge_fact"] = (
                        original[owner.owner_key]["edge_fact_by_memory_id"][identifier],
                        revised[owner.owner_key]["edge_fact_by_memory_id"][identifier],
                    )
                for name, (old, new) in values.items():
                    if old == new:
                        continue
                    if (owner.owner_key, slot.surface_key) not in allowed:
                        raise ValueError(
                            f"edit outside frozen inventory: {owner.owner_key}/{slot.surface_key}"
                        )
                    changes.append(
                        {
                            "owner_key": owner.owner_key,
                            "surface_key": slot.surface_key,
                            "field": name,
                            "before": old,
                            "after": new,
                            "before_sha256": hashlib.sha256(old.encode()).hexdigest(),
                            "after_sha256": hashlib.sha256(new.encode()).hexdigest(),
                        }
                    )
    return changes


def revise(
    manifest: BlindCorpusAuthoringManifest,
    authored: dict[str, Any],
    frozen: dict[str, Any],
    recipe: dict[str, Any],
) -> tuple[BlindCorpusAuthoringManifest, dict[str, Any], list[dict[str, Any]]]:
    inventory.compiler._validate_authored(manifest, authored)
    if set(recipe) != {"version", "description", "temporal_replacements", "owners"}:
        raise ValueError("unexpected recipe fields")
    if not set(recipe["owners"]) <= {owner.owner_key for owner in manifest.owners}:
        raise ValueError("unknown recipe owner")
    revised = deepcopy(authored)
    surfaces = {owner["owner_key"]: owner for owner in revised["owners"]}
    frozen_owners = {owner["owner_key"]: owner for owner in frozen["owners"]}
    owners = []
    for owner in manifest.owners:
        policy = recipe["owners"].get(owner.owner_key, {})
        if set(policy) - {"entity_names", "memories", "queries"}:
            raise ValueError("unexpected owner policy fields")
        item = surfaces[owner.owner_key]
        names = {
            e.surface_key: item["entity_names_by_id"][e.entity_id]
            for e in owner.entities
        }
        replacements = {}
        for key, value in policy.get("entity_names", {}).items():
            if (
                key not in {"entity-one-hop-anchor", "entity-branch-target"}
                or key not in names
            ):
                raise ValueError("unknown rename entity")
            replacements[names[key]] = value
            names[key] = value
        candidates = {
            slot["surface_key"] for slot in frozen_owners[owner.owner_key]["slots"]
        }
        updated = owner.model_dump(mode="json")
        consumed_memories, consumed_queries = set(), set()
        for field, id_field, mapping in FIELDS:
            for slot in updated[field]:
                key = slot["surface_key"]
                identifier = slot[id_field]
                if field == "entities":
                    item[mapping][identifier] = names[key]
                    if key in policy.get("entity_names", {}):
                        slot["semantic_brief"] = (
                            "文化活动正式签发的纪念证书，可由个人创作图案和版面"
                            if key == "entity-one-hop-anchor"
                            else "可签发证件的出入境管理机构，同时主办文化活动并签发纪念证书"
                        )
                    continue
                if key in candidates:
                    item[mapping][identifier] = _replace_names(
                        item[mapping][identifier], replacements
                    )
                    if field == "memories":
                        item["edge_fact_by_memory_id"][identifier] = _replace_names(
                            item["edge_fact_by_memory_id"][identifier], replacements
                        )
                if key == "memory-temporary-residence":
                    text = item[mapping][identifier]
                    for old, new in recipe["temporal_replacements"]:
                        text = text.replace(old, new)
                    if "2026年4月1日" not in text:
                        text += "2026年4月1日起不再临住。"
                    if "之前" in text or any(
                        date not in text
                        for date in ("2026年2月1日", "2026年3月31日", "2026年4月1日")
                    ):
                        raise ValueError("unresolved residency boundary")
                    item[mapping][identifier] = text
                    slot["semantic_brief"] = (
                        "主人临住从2026年2月1日起，持续到3月31日（含当天）；4月1日起结束。城市仍使用原临住城市的显示名。"
                    )
                if key == "query-temporary-as-of":
                    text = item[mapping][identifier]
                    for old in (
                        "2026年3月的时候",
                        "2026年3月期间",
                        "2026年3月那段时间",
                    ):
                        text = text.replace(old, "2026年3月15日当天")
                    if "2026年3月15日" not in text:
                        raise ValueError("unresolved as-of query date")
                    item[mapping][identifier] = text
                    slot["semantic_brief"] = (
                        "询问2026年3月15日主人临时住在哪座城市，不提供城市答案。"
                    )
                if key in policy.get("memories", {}) and field == "memories":
                    patch = policy["memories"][key]
                    if set(patch) != {"text", "edge_fact"}:
                        raise ValueError(
                            "memory recipe may only edit wording and edge fact"
                        )
                    item[mapping][identifier] = patch["text"].format_map(names)
                    item["edge_fact_by_memory_id"][identifier] = patch[
                        "edge_fact"
                    ].format_map(names)
                    slot["semantic_brief"] += (
                        "；明确区分创作与签发、不同获取环节，以及旧版失效或退养后重新获取；端点与关系类型不变。"
                    )
                    consumed_memories.add(key)
                if key in policy.get("queries", {}) and field == "queries":
                    item[mapping][identifier] = policy["queries"][key].format_map(names)
                    consumed_queries.add(key)
        if consumed_memories != set(
            policy.get("memories", {})
        ) or consumed_queries != set(policy.get("queries", {})):
            raise ValueError("unknown recipe surface key")
        owners.append(updated)
    repaired_manifest = BlindCorpusAuthoringManifest.model_validate(
        {
            **manifest.model_dump(mode="json"),
            "version": "1.4.2",
            "suite": "doppel-evidence-rich-blind-zh-v1-bounded-revised-host-manifest",
            "owners": owners,
        }
    )
    revised.update(
        {
            "runner": "doppel.evidence-rich-blind-bounded-revision.v1",
            "parent_authoring_provenance": {
                "runner": authored.get("runner"),
                "implementation_commit": authored.get("implementation_commit"),
                "generated_at": authored.get("generated_at"),
                "acquisition": deepcopy(authored.get("acquisition", {})),
            },
            "acquisition": {"provider_calls": 0, "tokens": 0},
            "manifest_fingerprint": repaired_manifest.fingerprint,
            "review_complete": False,
            "retrieval_opened": False,
            "quality_metrics_available": False,
            "curation": {
                "method": "assistant_bounded_text_repair",
                "recipe_version": recipe["version"],
                "independent_review_passed": False,
            },
        }
    )
    revised.pop("implementation_commit", None)
    revised.pop("generated_at", None)
    changes = validate_revision(manifest, repaired_manifest, authored, revised, frozen)
    # Every relation's original endpoint identities must remain explicit after edits.
    for owner in repaired_manifest.owners:
        item = surfaces[owner.owner_key]
        names = {
            e.surface_key: item["entity_names_by_id"][e.entity_id]
            for e in owner.entities
        }
        for memory in owner.memories:
            if not memory.relation_type:
                continue
            for endpoint in (memory.source_entity_key, memory.target_entity_key):
                for mapping in ("memory_content_by_id", "edge_fact_by_memory_id"):
                    if names[endpoint] not in item[mapping][memory.memory_id]:
                        raise ValueError(
                            f"relation endpoint missing: {owner.owner_key}/{memory.surface_key}"
                        )
    return repaired_manifest, revised, changes


def _read_bound(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"source hash mismatch: {path.name}")
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--output-prefix", type=Path, default=PREFIX)
    args = parser.parse_args()
    paths = [
        Path(f"{args.output_prefix}-{suffix}.json")
        for suffix in ("manifest", "surfaces", "diff")
    ]
    if any(path.exists() for path in paths):
        raise FileExistsError(
            "revision output exists; preserve it and select a new prefix"
        )
    authored = _read_bound(inventory.source.AUTHORED, inventory.AUTHORED_SHA256)
    _read_bound(inventory.source.REVIEW, inventory.REVIEW_SHA256)
    frozen = _read_bound(inventory.OUTPUT, INVENTORY_SHA256)
    manifest = inventory.source.build_manifest()
    if manifest.fingerprint != inventory.MANIFEST_SHA256:
        raise ValueError("original manifest changed")
    raw_recipe = args.recipe.read_bytes()
    recipe = json.loads(raw_recipe)
    repaired_manifest, revised, changes = revise(manifest, authored, frozen, recipe)
    revised["implementation_commit"] = inventory.source.acquire._git_commit_hash()
    binding = {
        **frozen["source"],
        "inventory_sha256": INVENTORY_SHA256,
        "recipe_sha256": hashlib.sha256(raw_recipe).hexdigest(),
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
    }
    revised["curation"]["source"] = binding
    payloads = [repaired_manifest.model_dump(mode="json"), revised]
    encoded = [
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n" for payload in payloads
    ]
    report = {
        "runner": "doppel.evidence-rich-blind-bounded-revision-diff.v1",
        "status": "revised_semantic_review_pending",
        "source": binding,
        "revised_manifest_sha256": hashlib.sha256(encoded[0].encode()).hexdigest(),
        "revised_surfaces_sha256": hashlib.sha256(encoded[1].encode()).hexdigest(),
        "revised_manifest_fingerprint": repaired_manifest.fingerprint,
        "authority_fingerprint": inventory.authority_fingerprint(repaired_manifest),
        "changes": changes,
        "summary": {
            "changed_surface_slots": len(
                {(c["owner_key"], c["surface_key"]) for c in changes}
            ),
            "changed_fields": dict(Counter(c["field"] for c in changes)),
            "candidate_surface_slots": frozen["summary"]["candidate_surface_slots"],
        },
        "original_findings": frozen["findings"],
        "gate": {
            "corpus_acceptance_granted": False,
            "compilation_allowed": False,
            "retrieval_opened": False,
            "quality_metrics_available": False,
        },
        "usage": {"provider_calls": 0, "tokens": 0},
    }
    encoded.append(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for path, text in zip(paths, encoded, strict=True):
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print(f"output: {path}")
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
