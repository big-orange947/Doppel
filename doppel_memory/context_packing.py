"""Opt-in lossless metadata factoring for already-authorized context items.

No retrieval, summarization, question/label access or authority decisions. The
wire format changes; hosts must explicitly teach their consumer this envelope.
This is not installed into recall, AML search or any Reader by default.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

FORMAT = "doppel.shared-context.v1"
SHAREABLE = frozenset(
    {"scope_key", "channel", "temporal_status", "valid_from", "valid_to"}
)


def encode(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


def _validate(items: list[dict[str, Any]]) -> None:
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("context items must be objects")
    for item in items:
        if any(
            not isinstance(item.get(key), str) or not item[key]
            for key in ("scope_key", "memory_id")
        ):
            raise ValueError("explicit scope and memory identities required")
        if not isinstance(item.get("text"), str):
            raise TypeError("original source text required")
    if len({item["scope_key"] for item in items}) > 1:
        raise ValueError("context packing requires one authorized exact scope")
    if len({item["memory_id"] for item in items}) != len(items):
        raise ValueError("duplicate context identity")


def unpack_context(payload: Any) -> list[dict[str, Any]]:
    """Decode without guessing missing fields or overriding item metadata."""
    bound = json.loads(encode(payload))
    if isinstance(bound, list):
        items = bound
    else:
        if (
            not isinstance(bound, dict)
            or set(bound) != {"format", "shared", "items"}
            or bound["format"] != FORMAT
        ):
            raise ValueError("unknown shared-context envelope")
        shared, entries = bound["shared"], bound["items"]
        if (
            not isinstance(shared, dict)
            or not set(shared) <= SHAREABLE
            or not isinstance(entries, list)
        ):
            raise ValueError("invalid shared-context metadata")
        if any(
            not isinstance(item, dict) or set(item) & set(shared) for item in entries
        ):
            raise ValueError("ambiguous per-item/shared context metadata")
        items = [{**shared, **item} for item in entries]
    _validate(items)
    return items


def _payload(items: list[dict[str, Any]], shared: dict[str, Any]) -> Any:
    compact = {
        "format": FORMAT,
        "shared": shared,
        "items": [
            {key: value for key, value in item.items() if key not in shared}
            for item in items
        ],
    }
    # Format overhead cannot make a previously fitting context exceed its budget.
    return compact if len(encode(compact)) < len(encode(items)) else items


@dataclass(frozen=True)
class PackedContext:
    payload: Any
    selected_ranks: tuple[int, ...]
    baseline_ranks: tuple[int, ...]
    wire_bytes: int
    baseline_bytes: int
    mode: str


def pack_context_items(
    candidates: Sequence[Mapping[str, Any]],
    *,
    mode: Literal["retain", "repack"] = "retain",
    byte_limit: int = 24_000,
    item_limit: int = 20,
    candidate_limit: int = 80,
) -> PackedContext:
    """Same ordered sources/budgets; factor only redundant context metadata.

    retain: seed the original whole-item ranked-fit selection, then fill freed
    bytes in original rank order, never displacing an old item. repack: rescan
    from scratch using factored byte costs; this may displace prior selections.
    Neither mode truncates a source or factors actor/role/authority/time labels.
    """
    if (
        mode not in {"retain", "repack"}
        or any(type(v) is not int or v < 1 for v in (item_limit, candidate_limit))
        or type(byte_limit) is not int
        or byte_limit < 2
    ):
        raise ValueError("valid packing mode and positive integer bounds required")
    snapshot = [dict(item) for item in candidates[:candidate_limit]]
    items = json.loads(encode(snapshot))
    if items != snapshot:
        raise ValueError("context metadata must roundtrip as JSON without coercion")
    _validate(items)
    baseline: list[int] = []
    for rank, item in enumerate(items):
        if len(baseline) == item_limit:
            break
        if len(encode([items[i] for i in [*baseline, rank]])) <= byte_limit:
            baseline.append(rank)
    shared = {
        key: items[0][key]
        for key in sorted(SHAREABLE)
        if items
        and all(key in item and item[key] == items[0].get(key) for item in items)
    }
    chosen = baseline.copy() if mode == "retain" else []
    for rank in range(len(items)):
        if rank in chosen:
            continue
        if len(chosen) == item_limit:
            break
        proposed = sorted([*chosen, rank])
        if len(encode(_payload([items[i] for i in proposed], shared))) <= byte_limit:
            chosen = proposed
    selected = [items[i] for i in chosen]
    payload = _payload(selected, shared)
    if unpack_context(payload) != selected:
        raise ValueError("context factoring failed exact roundtrip")
    return PackedContext(
        payload=payload,
        selected_ranks=tuple(i + 1 for i in chosen),
        baseline_ranks=tuple(i + 1 for i in baseline),
        wire_bytes=len(encode(payload)),
        baseline_bytes=len(encode([items[i] for i in baseline])),
        mode=mode,
    )
