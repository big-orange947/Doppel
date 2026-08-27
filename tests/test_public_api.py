"""Compatibility snapshots for the documented root-package API."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import doppel_memory as doppel

ROOT = Path(__file__).resolve().parents[1]

MODEL_FIELDS = {
    "BatchCheckpoint": (
        "cursor",
        "task_name",
        "task_version",
        "schema_version",
        "metadata",
    ),
    "BatchProposalPlan": ("proposals", "next_checkpoint"),
    "BatchReadLimits": ("max_pages", "max_messages", "max_page_size"),
    "BatchRunResult": (
        "proposals",
        "write_results",
        "errors",
        "task",
        "task_version",
        "run_id",
        "scope",
        "window",
        "checkpoint_schema_version",
        "history_pages_read",
        "history_messages_read",
        "committable_checkpoint",
    ),
    "ChatMessage": (
        "actor",
        "text",
        "at",
        "event_id",
        "message_id",
        "sender_id",
        "message_type",
        "reply_to_id",
        "quoted_message_id",
        "thread_id",
        "thread_root_id",
        "attachments",
        "raw",
        "parts",
    ),
    "ContentPart": ("type", "text", "media", "metadata"),
    "ContentResolution": ("message", "derived_parts", "errors"),
    "ContentResolutionError": ("resolver", "error_type", "message"),
    "IMImportBatch": (
        "format_version",
        "source",
        "source_version",
        "batch_id",
        "exported_at",
        "cursor",
        "items",
        "metadata",
    ),
    "IMImportItem": ("scope", "message", "source_id", "metadata"),
    "MemoryFilter": (
        "kinds",
        "actors",
        "authorities",
        "exclude_authorities",
        "exclude_actors",
        "states",
        "include_inactive",
        "tags",
        "importance_min",
        "time_from",
        "time_to",
    ),
    "MediaRef": (
        "media_id",
        "uri",
        "mime_type",
        "filename",
        "size_bytes",
        "sha256",
        "width",
        "height",
        "duration_ms",
        "metadata",
    ),
    "MemoryProposal": (
        "scope",
        "content",
        "kind",
        "actor",
        "authority",
        "confidence",
        "proposed_state",
        "tags",
        "importance",
        "idempotency_key",
        "source_event_id",
        "source_message_id",
        "processor",
        "processor_version",
        "derived_chain",
        "created_at",
        "metadata",
    ),
    "MemoryRecord": (
        "memory_id",
        "kind",
        "scope",
        "content",
        "actor",
        "authority",
        "state",
        "tags",
        "importance",
        "idempotency_key",
        "source_event_id",
        "source_message_id",
        "extractor",
        "created_at",
        "updated_at",
        "version",
        "metadata",
    ),
    "MemoryScope": (
        "user_id",
        "agent_id",
        "platform",
        "chat_type",
        "chat_id",
        "extra_dimensions",
    ),
    "RecallResult": (
        "fact",
        "kind",
        "scope",
        "memory_id",
        "actor",
        "authority",
        "source_event_id",
        "source_message_id",
        "source_episode",
        "extractor",
        "extracted_at",
        "raw_text",
        "derived_chain",
        "valid_at",
        "similarity",
        "state",
    ),
    "StoreCapabilities": (
        "semantic_search",
        "substring_search",
        "full_text_search",
        "temporal_search",
        "graph_relations",
        "metadata_filter",
        "hard_delete",
        "transactions",
        "reranking",
        "pagination",
    ),
    "StoreConformanceCheck": (
        "name",
        "status",
        "capability",
        "issues",
    ),
    "StoreConformanceConfig": (
        "run_id",
        "checks",
        "required_capabilities",
    ),
    "StoreConformanceReport": (
        "schema_version",
        "run_id",
        "store",
        "capabilities",
        "checks",
        "passed_count",
        "skipped_count",
        "failed_count",
    ),
    "StyleMinerConfig": (
        "min_messages",
        "page_size",
        "accepted_message_types",
        "target_scope",
        "short_message_chars",
        "phrase_ngram_min",
        "phrase_ngram_max",
        "min_phrase_messages",
        "min_phrase_ratio",
        "max_common_phrases",
        "max_source_ids",
    ),
    "StyleDirective": (
        "feature",
        "instruction",
        "evidence",
        "confidence",
        "priority",
    ),
    "StyleGuidance": (
        "schema_version",
        "professor",
        "professor_version",
        "profile_fingerprint",
        "config_fingerprint",
        "source_analyzer",
        "source_analyzer_version",
        "source_message_count",
        "usable",
        "directives",
        "prompt",
        "omitted_features",
        "warnings",
    ),
    "StyleProfessorConfig": (
        "min_reliable_messages",
        "full_confidence_messages",
        "max_prompt_chars",
        "include_common_phrases",
        "max_common_phrases",
        "max_phrase_chars",
    ),
    "StyleProfile": (
        "schema_version",
        "analyzer",
        "analyzer_version",
        "message_count",
        "character_count",
        "average_message_length",
        "median_message_length",
        "short_message_threshold",
        "short_message_ratio",
        "question_ratio",
        "exclamation_ratio",
        "emoji_ratio",
        "multiline_ratio",
        "terminal_punctuation_ratio",
        "common_phrases",
        "summary",
    ),
    "StyleQualityConfig": (
        "min_candidate_messages",
        "passing_score",
    ),
    "StyleQualityReport": (
        "schema_version",
        "evaluator",
        "evaluator_version",
        "reference_profile_fingerprint",
        "config_fingerprint",
        "candidate_input_count",
        "candidate_message_count",
        "sufficient_samples",
        "feature_scores",
        "observed",
        "aggregate_score",
        "passed",
        "warnings",
    ),
    "WriteResult": ("status", "record", "error_code", "message"),
}

SIGNATURES = {
    "BatchProposalPolicy.evaluate": (
        ("proposal", "POSITIONAL_OR_KEYWORD"),
        ("context", "POSITIONAL_OR_KEYWORD"),
    ),
    "ContentResolver.resolve": (("message", "POSITIONAL_OR_KEYWORD"),),
    "DoppelClient.__init__": (
        ("store", "POSITIONAL_OR_KEYWORD"),
        ("backend", "KEYWORD_ONLY"),
        ("retrieval_strategy", "KEYWORD_ONLY"),
        ("reranker", "KEYWORD_ONLY"),
        ("candidate_multiplier", "KEYWORD_ONLY"),
        ("backend_kwargs", "VAR_KEYWORD"),
    ),
    "DoppelClient.process": (
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("message", "POSITIONAL_OR_KEYWORD"),
        ("processors", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
        ("hooks", "KEYWORD_ONLY"),
        ("allowed_scopes", "KEYWORD_ONLY"),
    ),
    "DoppelClient.materials": (
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("query", "POSITIONAL_OR_KEYWORD"),
        ("scopes", "KEYWORD_ONLY"),
        ("memory_limit", "KEYWORD_ONLY"),
        ("style_sample_limit", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
        ("style_professor", "KEYWORD_ONLY"),
    ),
    "DoppelClient.run_batch_task": (
        ("task", "POSITIONAL_OR_KEYWORD"),
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("window", "POSITIONAL_OR_KEYWORD"),
        ("checkpoint", "KEYWORD_ONLY"),
        ("history", "KEYWORD_ONLY"),
        ("memories", "KEYWORD_ONLY"),
        ("read_scopes", "KEYWORD_ONLY"),
        ("allowed_scopes", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
        ("hooks", "KEYWORD_ONLY"),
        ("read_limits", "KEYWORD_ONLY"),
        ("run_id", "KEYWORD_ONLY"),
    ),
    "DeterministicStyleAnalyzer.analyze": (
        ("messages", "POSITIONAL_OR_KEYWORD"),
        ("config", "KEYWORD_ONLY"),
    ),
    "MemoryBatchTask.propose": (("context", "POSITIONAL_OR_KEYWORD"),),
    "MemoryProcessor.process": (
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("message", "POSITIONAL_OR_KEYWORD"),
    ),
    "MemoryStore.put": (
        ("record", "POSITIONAL_OR_KEYWORD"),
        ("idempotency_key", "KEYWORD_ONLY"),
    ),
    "MemoryStore.scan": (
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("filters", "KEYWORD_ONLY"),
        ("cursor", "KEYWORD_ONLY"),
        ("limit", "KEYWORD_ONLY"),
    ),
    "MemoryStore.search": (
        ("query", "POSITIONAL_OR_KEYWORD"),
        ("scopes", "POSITIONAL_OR_KEYWORD"),
        ("filters", "KEYWORD_ONLY"),
        ("limit", "KEYWORD_ONLY"),
    ),
    "PersonaMaterialsBuilder.__init__": (
        ("retriever", "POSITIONAL_OR_KEYWORD"),
        ("store", "KEYWORD_ONLY"),
    ),
    "PersonaMaterialsBuilder.build": (
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("query", "POSITIONAL_OR_KEYWORD"),
        ("scopes", "KEYWORD_ONLY"),
        ("memory_limit", "KEYWORD_ONLY"),
        ("style_sample_limit", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
        ("style_professor", "KEYWORD_ONLY"),
    ),
    "ProposalPolicy.evaluate": (
        ("proposal", "POSITIONAL_OR_KEYWORD"),
        ("message", "POSITIONAL_OR_KEYWORD"),
    ),
    "Reranker.rerank": (
        ("query", "POSITIONAL_OR_KEYWORD"),
        ("candidates", "POSITIONAL_OR_KEYWORD"),
        ("limit", "KEYWORD_ONLY"),
    ),
    "RetrievalStrategy.search": (
        ("store", "POSITIONAL_OR_KEYWORD"),
        ("query", "POSITIONAL_OR_KEYWORD"),
        ("scopes", "POSITIONAL_OR_KEYWORD"),
        ("filters", "KEYWORD_ONLY"),
        ("limit", "KEYWORD_ONLY"),
    ),
    "ScopedHistoryReader.read": (
        ("cursor", "KEYWORD_ONLY"),
        ("limit", "KEYWORD_ONLY"),
        ("actors", "KEYWORD_ONLY"),
        ("time_from", "KEYWORD_ONLY"),
        ("time_to", "KEYWORD_ONLY"),
    ),
    "ScopedMemoryReader.get": (
        ("scope", "POSITIONAL_OR_KEYWORD"),
        ("memory_id", "POSITIONAL_OR_KEYWORD"),
    ),
    "ScopedMemoryReader.recall": (
        ("query", "POSITIONAL_OR_KEYWORD"),
        ("filters", "KEYWORD_ONLY"),
        ("limit", "KEYWORD_ONLY"),
    ),
    "StyleAnalyzer.analyze": (
        ("messages", "POSITIONAL_OR_KEYWORD"),
        ("config", "KEYWORD_ONLY"),
    ),
    "StyleMiner.__init__": (
        ("config", "POSITIONAL_OR_KEYWORD"),
        ("analyzer", "KEYWORD_ONLY"),
    ),
    "StyleMiner.propose": (("context", "POSITIONAL_OR_KEYWORD"),),
    "StyleProfessor.__init__": (("config", "POSITIONAL_OR_KEYWORD"),),
    "StyleProfessor.compile": (("profile", "POSITIONAL_OR_KEYWORD"),),
    "StyleGuideCompiler.compile": (("profile", "POSITIONAL_OR_KEYWORD"),),
    "StyleQualityEvaluator.__init__": (("config", "POSITIONAL_OR_KEYWORD"),),
    "StyleQualityEvaluator.evaluate": (
        ("reference", "POSITIONAL_OR_KEYWORD"),
        ("candidates", "POSITIONAL_OR_KEYWORD"),
    ),
    "audit_store": (
        ("store", "POSITIONAL_OR_KEYWORD"),
        ("config", "KEYWORD_ONLY"),
    ),
    "resolve_content": (
        ("message", "POSITIONAL_OR_KEYWORD"),
        ("resolvers", "POSITIONAL_OR_KEYWORD"),
    ),
}


def test_root_exports_match_versioned_manifest() -> None:
    manifest = json.loads((ROOT / "docs" / "public-api.json").read_text("utf-8"))
    stable = manifest["tiers"]["stable"]
    provisional = manifest["tiers"]["provisional"]
    metadata = manifest["metadata"]
    expected = [*stable, *provisional, *metadata]
    assert manifest["manifest_version"] == 1
    assert manifest["release"] == doppel.__version__
    assert len(expected) == len(set(expected))
    assert set(stable).isdisjoint(provisional)
    assert set(doppel.__all__) == set(expected)
    assert len(doppel.__all__) == len(set(doppel.__all__))
    assert all(hasattr(doppel, name) for name in expected)


def test_wire_model_field_order_is_reviewed_explicitly() -> None:
    actual = {name: tuple(getattr(doppel, name).model_fields) for name in MODEL_FIELDS}
    assert actual == MODEL_FIELDS


def test_extension_protocol_signature_shape_is_reviewed_explicitly() -> None:
    actual = {name: _parameter_shape(_resolve(name)) for name in SIGNATURES}
    assert actual == SIGNATURES


def test_critical_defaults_and_enum_values_are_stable() -> None:
    assert (
        inspect.signature(doppel.DoppelClient.__init__).parameters["backend"].default
        == "sqlite"
    )
    assert (
        inspect.signature(doppel.DoppelClient.process).parameters["processors"].default
        is None
    )
    assert inspect.signature(doppel.MemoryStore.scan).parameters["cursor"].default == ""
    assert inspect.signature(doppel.MemoryStore.scan).parameters["limit"].default == 100
    assert (
        inspect.signature(doppel.ScopedHistoryReader.read).parameters["limit"].default
        == 500
    )
    assert doppel.BatchReadLimits().model_dump() == {
        "max_pages": 100,
        "max_messages": 50_000,
        "max_page_size": 2_000,
    }
    assert doppel.StyleMinerConfig().min_messages == 20
    assert doppel.StyleMinerConfig().target_scope == "conversation"
    assert doppel.StyleProfessorConfig().include_common_phrases is False
    assert doppel.StyleProfessorConfig().max_prompt_chars == 800
    assert doppel.StyleQualityConfig().min_candidate_messages == 20
    assert doppel.ChatMessage().parts == []
    assert [item.value for item in doppel.MemoryState] == [
        "candidate",
        "confirmed",
        "rejected",
        "superseded",
        "expired",
    ]
    assert [item.value for item in doppel.WriteStatus] == [
        "created",
        "updated",
        "duplicate",
        "skipped",
        "failed",
    ]


def test_custom_store_abstract_surface_does_not_accidentally_expand() -> None:
    assert doppel.MemoryStore.__abstractmethods__ == {
        "capabilities",
        "forget",
        "get",
        "health",
        "is_enabled",
        "list_recent_owner_messages",
        "put",
        "search",
        "transition",
    }


def _resolve(path: str):
    if "." not in path:
        return getattr(doppel, path)
    owner_name, attribute = path.split(".", maxsplit=1)
    return getattr(getattr(doppel, owner_name), attribute)


def _parameter_shape(callable_object) -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, parameter.kind.name)
        for name, parameter in inspect.signature(callable_object).parameters.items()
        if name != "self"
    )
