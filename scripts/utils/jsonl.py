"""APA_citation_finder :: utils/jsonl.py
Thread-safe JSONL appends / reads (evidence-chain logs).
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Iterator

_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_jsonl(path: str, record: dict) -> None:
    """Append one JSON record to a JSONL file (creates parent dirs)."""
    if not path:
        return
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def write_claims(path: str, claims: list[dict]) -> None:
    """Write claims preserving the file's format: JSONL for .jsonl,
    JSON array otherwise. Keeps Stage 2-4 CLIs from corrupting
    claims.jsonl into a JSON array."""
    if str(path).endswith(".jsonl"):
        with open(path, "w", encoding="utf-8") as f:
            for c in claims:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    else:
        write_json(path, claims)


def read_claims(path: str) -> list[dict]:
    """Read a claim file: JSONL (one claim per line) or JSON array/object.

    The Stage-1 CLI writes claims.jsonl; other stages accept both so old
    artifacts and hand-written JSON keep working.
    """
    if not os.path.exists(path):
        return []
    if path.endswith(".jsonl"):
        return read_jsonl(path)
    try:
        data = load_json(path)
    except Exception:
        return read_jsonl(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("claims"), list):
        return data["claims"]
    return []


def read_jsonl(path: str) -> list[dict]:
    """Read all records from a JSONL file; skips malformed lines."""
    out: list[dict] = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def write_json(path: str, data: Any) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
