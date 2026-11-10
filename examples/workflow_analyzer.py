"""Explicit reference-analyzer session with a durable single-writer call ledger."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx

from doppel_memory import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    ReferencePersonalMemoryAnalyzer,
)


class WorkflowAnalyzerSession:
    """Reserve before generation, never refund/retry; ledger contains no requests.

    Requires exclusive host ownership. A missing response/usage is unknown billing,
    not free. This is a call cap, not a token/currency cap or exactly-once transport.
    """

    def __init__(
        self,
        path: Path,
        *,
        binding: str,
        config: OpenAICompatibleStructuredOutputConfig,
        api_key: str,
        max_calls: int = 2,
        client: httpx.AsyncClient | None = None,
    ):
        if (
            not api_key.strip()
            or type(max_calls) is not int
            or not 1 <= max_calls <= 20
        ):
            raise ValueError("key and call cap between 1 and 20 required")
        self.path, self.new_calls = path, 0
        self._header = {
            "binding": hashlib.sha256(
                (binding + config.fingerprint).encode()
            ).hexdigest(),
            "max_calls": max_calls,
            "schema": 1,
        }
        if path.exists():
            self.events = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            if not self.events or self.events[0] != self._header:
                raise ValueError("analyzer ledger identity or cap changed")
        else:
            self.events = []
            self._append(self._header)
        # Corrupt/partial ledgers fail closed rather than resetting call accounting.
        attempts = [
            event["attempt"]
            for event in self.events[1:]
            if event.get("event") == "reserved"
        ]
        if attempts != list(range(1, len(attempts) + 1)) or len(attempts) > max_calls:
            raise ValueError("invalid analyzer ledger reservations")
        if any(
            event.get("event") not in {"reserved", "usage", "completed", "failed"}
            for event in self.events[1:]
        ):
            raise ValueError("invalid analyzer ledger event")
        used, finished = set(), set()
        for event in self.events[1:]:
            attempt = event.get("attempt")
            if type(attempt) is not int or attempt not in attempts:
                raise ValueError("unbound analyzer ledger event")
            if event["event"] == "usage":
                tokens = event.get("tokens")
                if (
                    attempt in used
                    or not isinstance(tokens, dict)
                    or any(
                        type(value) is not int or value < 0 for value in tokens.values()
                    )
                ):
                    raise ValueError("invalid analyzer usage record")
                used.add(attempt)
            if event["event"] in {"completed", "failed"}:
                if attempt in finished:
                    raise ValueError("duplicate analyzer completion")
                finished.add(attempt)
        self.model = OpenAICompatibleStructuredOutputModel(
            config, api_key=api_key, client=client, usage_observer=self._usage
        )
        self.name, self.version = self.model.name, self.model.version
        self.analyzer = ReferencePersonalMemoryAnalyzer(self)
        self._active_attempt = 0

    def _append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(event)

    def _usage(self, usage) -> None:
        self._append(
            {"event": "usage", "attempt": self._active_attempt, "tokens": dict(usage)}
        )

    async def generate(self, request):
        if self._active_attempt:
            raise RuntimeError("concurrent analyzer calls are unsupported")
        calls = sum(event.get("event") == "reserved" for event in self.events)
        if calls >= self._header["max_calls"]:
            raise RuntimeError("durable analyzer call cap exhausted")
        self._append({"event": "reserved", "attempt": calls + 1})
        self.new_calls += 1
        self._active_attempt = calls + 1
        try:
            response = await self.model.generate(request)
            self._append({"event": "completed", "attempt": self._active_attempt})
            return response
        except Exception as exc:
            self._append(
                {
                    "event": "failed",
                    "attempt": self._active_attempt,
                    "error_type": type(exc).__name__,
                }
            )
            raise
        finally:
            self._active_attempt = 0

    def report(self) -> dict:
        calls = sum(event.get("event") == "reserved" for event in self.events)
        usages = [event for event in self.events if event.get("event") == "usage"]
        return {
            "new_calls": self.new_calls,
            "reserved_calls": calls,
            "max_calls": self._header["max_calls"],
            "usage_missing_calls": calls - len(usages),
            "observed_tokens": {
                key: sum(item["tokens"].get(key, 0) for item in usages)
                for key in {key for item in usages for key in item["tokens"]}
            },
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.model.aclose()
