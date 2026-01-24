from __future__ import annotations

import json
from typing import Any


class ProtocolError(ValueError):
    pass


def parse_json_line(line: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(line.decode("utf-8"))
    except Exception as e:
        raise ProtocolError(f"Invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ProtocolError("JSON message must be an object")
    return obj


def to_json_line(obj: dict[str, Any]) -> bytes:
    # JS8Call examples look like compact JSON with \n terminator.
    s = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    return (s + "\n").encode("utf-8")


def fragment_text(payload: str, fragment_size: int) -> list[str]:
    # No padding. Fragment size is in characters (as per your examples); payload is already string.
    if fragment_size <= 0:
        return [payload]
    return [payload[i:i + fragment_size] for i in range(0, len(payload), fragment_size)]
