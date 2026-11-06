"""
Feedback loop storage (spec sections 22-23).

Lightweight JSONL-file store (no DB dependency needed for this stage)
that records:
  - AI recommendation vs. employee override (human-in-the-loop)
  - campaign/outcome feedback (accepted/rejected, stayed/churned, etc.)

This is intentionally simple and file-based so it works out of the box
without extra infra; swap `_STORE_PATH` writes for a real DB later
without changing the public functions below (append_override,
append_outcome, load_overrides, load_outcomes) - callers don't need to
change.

None of this feeds back into the live model automatically yet (that is
future work per the spec: Historical Campaign Outcomes -> Campaign
Performance Analysis -> Next Best Action/Offer model). Today it just
captures clean, structured training data for that future step.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORE_DIR = BASE_DIR / "feedback_data"
STORE_DIR.mkdir(exist_ok=True)

OVERRIDES_PATH = STORE_DIR / "overrides.jsonl"
OUTCOMES_PATH = STORE_DIR / "outcomes.jsonl"

_lock = Lock()


def _append_jsonl(path: Path, record: dict) -> None:
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str))
            f.write("\n")


def _load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_override(
    customer_id: str,
    ai_recommendation: str,
    employee_decision: str,
    reason: str = "",
) -> dict:
    """
    Records a human override of the AI's recommended action/campaign
    (spec section 22). `customer_id` may be the dataset's customerID
    or a synthetic id ("manual-<hash>") for a customer entered via
    free text without a known ID.
    """

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_id": customer_id,
        "ai_recommendation": ai_recommendation,
        "employee_decision": employee_decision,
        "reason": reason,
    }
    _append_jsonl(OVERRIDES_PATH, record)
    return record


def append_outcome(
    customer_id: str,
    campaign_or_offer: str,
    accepted: bool = None,
    stayed: bool = None,
    revenue_change: float = None,
    notes: str = "",
) -> dict:
    """
    Records an eventual real-world outcome for a campaign/offer that
    was sent to a customer (spec section 23). All fields besides
    customer_id/campaign_or_offer are optional since outcomes often
    arrive incrementally (e.g. "accepted" known immediately, "stayed"
    only known a billing cycle later).
    """

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_id": customer_id,
        "campaign_or_offer": campaign_or_offer,
        "accepted": accepted,
        "stayed": stayed,
        "revenue_change": revenue_change,
        "notes": notes,
    }
    _append_jsonl(OUTCOMES_PATH, record)
    return record


def load_overrides() -> list:
    return _load_jsonl(OVERRIDES_PATH)


def load_outcomes() -> list:
    return _load_jsonl(OUTCOMES_PATH)
