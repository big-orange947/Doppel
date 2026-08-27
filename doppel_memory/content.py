"""Optional structured-content resolution without implicit persistence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from doppel_memory.models import ChatMessage, ContentPart


class ContentResolutionError(BaseModel):
    """One resolver failure retained without hiding successful resolvers."""

    resolver: str
    error_type: str
    message: str


class ContentResolution(BaseModel):
    """A resolved message copy plus derived parts and structured failures."""

    message: ChatMessage
    derived_parts: list[ContentPart] = Field(default_factory=list)
    errors: list[ContentResolutionError] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def changed(self) -> bool:
        return bool(self.derived_parts)


@runtime_checkable
class ContentResolver(Protocol):
    """Return additional derived parts; never write a Store or mutate the input."""

    name: str
    version: str

    async def resolve(self, message: ChatMessage) -> Sequence[ContentPart]: ...


async def resolve_content(
    message: ChatMessage,
    resolvers: Sequence[ContentResolver],
) -> ContentResolution:
    """Run resolvers in order and return a new message with provenance-bound parts."""
    working = message.model_copy(deep=True)
    derived_parts: list[ContentPart] = []
    errors: list[ContentResolutionError] = []
    for resolver in resolvers:
        fallback_name = type(resolver).__name__
        resolver_name = str(getattr(resolver, "name", "") or "").strip()
        resolver_version = str(getattr(resolver, "version", "") or "").strip()
        try:
            if not resolver_name:
                raise ValueError("content resolver name must not be empty")
            if not resolver_version:
                raise ValueError("content resolver version must not be empty")
            raw_parts = await resolver.resolve(working.model_copy(deep=True))
            if isinstance(raw_parts, (str, bytes)) or not isinstance(
                raw_parts, Sequence
            ):
                raise TypeError("content resolver must return a sequence of parts")
            resolved_parts = [
                _bind_provenance(
                    ContentPart.model_validate(raw_part),
                    resolver=resolver_name,
                    resolver_version=resolver_version,
                )
                for raw_part in raw_parts
            ]
            if resolved_parts:
                derived_parts.extend(resolved_parts)
                working = _append_parts(working, resolved_parts)
        except Exception as exc:  # noqa: BLE001 - resolver plugin boundary
            errors.append(
                ContentResolutionError(
                    resolver=resolver_name or fallback_name,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )
    return ContentResolution(
        message=working,
        derived_parts=derived_parts,
        errors=errors,
    )


def _bind_provenance(
    part: ContentPart,
    *,
    resolver: str,
    resolver_version: str,
) -> ContentPart:
    metadata: dict[str, Any] = dict(part.metadata)
    metadata["doppel_resolution"] = {
        "resolver": resolver,
        "resolver_version": resolver_version,
    }
    return part.model_copy(update={"metadata": metadata}, deep=True)


def _append_parts(
    message: ChatMessage, derived_parts: Sequence[ContentPart]
) -> ChatMessage:
    parts = [*message.parts, *derived_parts]
    texts = list(
        dict.fromkeys(
            text
            for text in (
                message.text,
                *(part.text for part in derived_parts),
            )
            if text
        )
    )
    values = message.model_dump(mode="python")
    values.update({"text": "\n".join(texts), "parts": parts})
    return ChatMessage.model_validate(values)
