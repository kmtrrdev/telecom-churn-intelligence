"""
AI Sessions store (Phase 6 spec: persistent chat sessions, history,
rename/delete/search/pin, resume previous conversations).

Kept file-based (JSON, one file per session) like feedback_store.py /
dataset_store.py elsewhere in this app - no DB dependency needed.

Two session `kind`s are supported and are kept completely separate,
mirroring the dataset-vs-customer split already in app/main.py:
  - "customer": single-customer chat (collected fields + analysis)
  - "dataset":  dataset/CSV assistant (upload signature + chat only)
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORE_DIR = BASE_DIR / "data" / "sessions"
STORE_DIR.mkdir(parents=True, exist_ok=True)

_lock = Lock()

VALID_KINDS = {"customer", "dataset"}


def _path(session_id: str) -> Path:
    return STORE_DIR / f"{session_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_title(kind: str) -> str:
    label = "محادثة عميل" if kind == "customer" else "محادثة داتاسِت"
    return f"{label} — {datetime.now().strftime('%d/%m %H:%M')}"


def create_session(kind: str, title: str = "", state: dict | None = None) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid session kind: {kind}")
    session_id = uuid.uuid4().hex[:12]
    record = {
        "id": session_id,
        "kind": kind,
        "title": title.strip() or _default_title(kind),
        "pinned": False,
        "created_at": _now(),
        "updated_at": _now(),
        "state": state or {},
    }
    with _lock:
        _path(session_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return record


def get_session(session_id: str) -> dict | None:
    p = _path(session_id)
    if not p.exists():
        return None
    with _lock:
        return json.loads(p.read_text(encoding="utf-8"))


def update_session(
    session_id: str,
    title: str | None = None,
    pinned: bool | None = None,
    state: dict | None = None,
) -> dict | None:
    record = get_session(session_id)
    if record is None:
        return None
    if title is not None and title.strip():
        record["title"] = title.strip()
    if pinned is not None:
        record["pinned"] = bool(pinned)
    if state is not None:
        record["state"] = state
    record["updated_at"] = _now()
    with _lock:
        _path(session_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return record


def delete_session(session_id: str) -> bool:
    p = _path(session_id)
    if not p.exists():
        return False
    with _lock:
        p.unlink()
    return True


def list_sessions(kind: str | None = None, search: str = "") -> list[dict]:
    records = []
    with _lock:
        files = list(STORE_DIR.glob("*.json"))
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if kind and record.get("kind") != kind:
            continue
        if search and search.lower() not in record.get("title", "").lower():
            continue
        # Don't ship the full state blob in the list view - keep it light.
        records.append(
            {
                "id": record["id"],
                "kind": record["kind"],
                "title": record["title"],
                "pinned": record.get("pinned", False),
                "created_at": record["created_at"],
                "updated_at": record["updated_at"],
                "message_count": len(record.get("state", {}).get("history", [])),
            }
        )
    records.sort(key=lambda r: (not r["pinned"], r["updated_at"]), reverse=True)
    return records
