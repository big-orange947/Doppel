"""Structured IM content representation and opt-in resolution."""

from __future__ import annotations

import pytest

from doppel_memory import (
    Actor,
    ChatMessage,
    ContentPart,
    MediaRef,
    resolve_content,
)


def _image_message() -> ChatMessage:
    return ChatMessage.of(
        Actor.OWNER,
        "",
        "2026-08-27T10:00:00Z",
        event_id="image-1",
        message_type="image",
        attachments=[{"legacy_file_id": "legacy-1"}],
        raw={"platform": "qq"},
        parts=[
            ContentPart(
                type="IMAGE",
                media=MediaRef(
                    media_id="qq-image-1",
                    uri="qq://media/image-1",
                    mime_type="IMAGE/PNG",
                    filename="photo.png",
                    size_bytes=42,
                    sha256="a" * 64,
                    width=640,
                    height=480,
                ),
                metadata={"platform_part_index": 0},
            )
        ],
    )


def test_structured_message_round_trips_without_replacing_legacy_fields() -> None:
    message = _image_message()
    restored = ChatMessage.model_validate_json(message.model_dump_json())

    assert message.text == ""
    assert message.parts[0].type == "image"
    assert message.parts[0].media is not None
    assert message.parts[0].media.mime_type == "image/png"
    assert restored == message
    assert restored.attachments == [{"legacy_file_id": "legacy-1"}]
    assert restored.raw == {"platform": "qq"}
    assert "parts=1" in restored.episode_line()


def test_text_parts_supply_the_legacy_text_projection_only_when_empty() -> None:
    projected = ChatMessage.of(
        Actor.OWNER,
        "",
        "2026-08-27T10:00:00Z",
        parts=[
            ContentPart(type="text", text="第一段"),
            ContentPart(type="text", text="第二段"),
            ContentPart(type="text", text="第一段"),
        ],
    )
    explicit = ChatMessage.of(
        Actor.OWNER,
        "显式文本",
        "2026-08-27T10:00:00Z",
        parts=[ContentPart(type="text", text="结构化文本")],
    )

    assert projected.text == "第一段\n第二段"
    assert explicit.text == "显式文本"


def test_structured_content_rejects_ambiguous_empty_values() -> None:
    with pytest.raises(ValueError, match="media_id or uri"):
        MediaRef()
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        MediaRef(media_id="bad-hash", sha256="not-a-hash")
    with pytest.raises(ValueError, match="content part type"):
        ContentPart(type="", text="value")
    with pytest.raises(ValueError, match="requires text, media, or metadata"):
        ContentPart(type="image")


class MutatingFailureResolver:
    name = "example.failure"
    version = "1"

    async def resolve(self, message):
        message.text = "resolver-local mutation"
        message.parts[0].metadata["resolver_mutation"] = True
        raise RuntimeError("OCR unavailable")


class OCRResolver:
    name = "example.ocr"
    version = "2"

    async def resolve(self, message):
        assert message.text == ""
        return [
            ContentPart(
                type="text",
                text="图片中的派生文字",
                metadata={"confidence": 0.91},
            )
        ]


class LabelResolver:
    name = "example.label"
    version = "1"

    async def resolve(self, message):
        assert message.text == "图片中的派生文字"
        return [ContentPart(type="label", metadata={"labels": ["screenshot"]})]


async def test_resolvers_are_isolated_composable_and_never_mutate_input() -> None:
    original = _image_message()
    resolution = await resolve_content(
        original,
        [MutatingFailureResolver(), OCRResolver(), LabelResolver()],
    )

    assert original.text == ""
    assert len(original.parts) == 1
    assert "resolver_mutation" not in original.parts[0].metadata
    assert resolution.message is not original
    assert resolution.message.text == "图片中的派生文字"
    assert resolution.message.message_type == "image"
    assert len(resolution.message.parts) == 3
    assert resolution.changed
    assert not resolution.ok
    assert len(resolution.derived_parts) == 2
    assert resolution.errors[0].resolver == "example.failure"
    assert resolution.errors[0].error_type == "RuntimeError"
    assert resolution.errors[0].message == "OCR unavailable"

    ocr_part = resolution.derived_parts[0]
    assert ocr_part.metadata["confidence"] == 0.91
    assert ocr_part.metadata["doppel_resolution"] == {
        "resolver": "example.ocr",
        "resolver_version": "2",
    }
    assert resolution.derived_parts[1].metadata["doppel_resolution"] == {
        "resolver": "example.label",
        "resolver_version": "1",
    }


class InvalidReturnResolver:
    name = "example.invalid"
    version = "1"

    async def resolve(self, message):
        del message
        return "not a part sequence"


async def test_invalid_resolver_output_is_structured_not_raised() -> None:
    resolution = await resolve_content(_image_message(), [InvalidReturnResolver()])
    assert not resolution.changed
    assert not resolution.ok
    assert resolution.errors[0].error_type == "TypeError"
    assert "sequence of parts" in resolution.errors[0].message


async def test_no_resolvers_returns_an_equal_independent_copy() -> None:
    original = _image_message()
    resolution = await resolve_content(original, [])
    assert resolution.ok
    assert not resolution.changed
    assert resolution.message == original
    assert resolution.message is not original
