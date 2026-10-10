"""Bounded allowlisted extraction-loss telemetry; never retain raw log text.

An empty report certifies no observed supported endpoint-warning events during
this invocation, not that every extraction was correct or every warning captured.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE: ContextVar[tuple[str, str] | None] = ContextVar(
    "graph_warning_record", default=None
)
_TEMPLATES = {
    "Source entity not found in nodes for edge relation: %s": "source",
    "Target entity not found in nodes for edge relation: %s": "target",
}
_RELATION_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")


class GraphExtractionWarnings(logging.Handler):
    def __init__(self, *, max_entries: int = 1024) -> None:
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("positive warning detail bound required")
        super().__init__(level=logging.WARNING)
        self.max_entries = max_entries
        self.entries: list[dict[str, str]] = []
        self.counts: Counter[str] = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        active = _ACTIVE.get()
        # Exact templates/argument shape only. Never format arbitrary records,
        # exceptions, headers, provider messages, or source/entity content.
        if (
            active is None
            or not record.name.startswith("graphiti_core.")
            or not isinstance(record.msg, str)
            or record.msg not in _TEMPLATES
            or not isinstance(record.args, tuple)
            or len(record.args) != 1
            or not isinstance(record.args[0], str)
            or _RELATION_NAME.fullmatch(record.args[0]) is None
        ):
            return
        endpoint = _TEMPLATES[record.msg]
        self.counts[endpoint] += 1
        if len(self.entries) < self.max_entries:
            scope, memory = active
            self.entries.append(
                {
                    "code": "graph_extraction_missing_endpoint",
                    "endpoint": endpoint,
                    "relation_type": record.args[0],
                    "scope_key": scope,
                    "memory_id": memory,
                }
            )

    @contextmanager
    def capture(self):
        logger = logging.getLogger("graphiti_core")
        logger.addHandler(self)
        try:
            yield self
        finally:
            logger.removeHandler(self)

    @contextmanager
    def indexing(self, scope_key: str, memory_id: str):
        token = _ACTIVE.set((scope_key, memory_id))
        try:
            yield
        finally:
            _ACTIVE.reset(token)

    def report(self):
        total = sum(self.counts.values())
        return {
            "coverage": "allowlisted-graphiti-endpoint-templates-this-invocation",
            "semantic_completeness_certified": False,
            "all_warning_classes_captured": False,
            "raw_log_text_retained": False,
            "observed_count": total,
            "counts_by_endpoint": dict(self.counts),
            "entries": [dict(entry) for entry in self.entries],
            "dropped_detail_count": total - len(self.entries),
        }
