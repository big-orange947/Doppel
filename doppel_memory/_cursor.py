"""Opaque cursor helpers shared by stable Store implementations."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime


def encode_cursor(created_at: datetime, memory_id: str) -> str:
    payload = json.dumps(
        [created_at.isoformat(), memory_id],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode())
        created_at, memory_id = json.loads(raw)
        parsed = datetime.fromisoformat(str(created_at))
        if parsed.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        return parsed, str(memory_id)
    except (
        binascii.Error,
        UnicodeDecodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("invalid memory page cursor") from exc
