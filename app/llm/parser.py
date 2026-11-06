"""
Structured Extraction - natural language -> CustomerInput fields.

The LLM's OTHER job (per the architecture rule): turn the employee's
free-text description into structured fields matching
app.schemas.CustomerInput. It must never invent values it wasn't
given - any field not explicitly stated is left out (null), and the
caller (Streamlit app / API) is responsible for asking the employee
for whatever is still missing after extraction.
"""

import re
import json

from app.llm.prompts import (  # noqa: F401 (re-exported for callers)
    REQUIRED_FIELDS,
    FIELD_HINTS_AR,
    EXTRACTION_SYSTEM_PROMPT_TEMPLATE,
)
from app.llm.conversation import get_client


def _strip_json_fences(text: str) -> str:

    text = text.strip()
    text = re.sub(r"^```(json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    return text.strip()


def _empty_extraction() -> dict:

    result = {field: None for field in REQUIRED_FIELDS}
    result["off_topic"] = False
    return result


def extract_customer_data(
    message: str, asked_fields: list = None, token: str = None
) -> dict:
    """
    Calls the LLM to turn the employee's latest message into a dict of
    CustomerInput-shaped fields (plus an "off_topic" flag). Fields the
    employee didn't address come back as None.

    `asked_fields` is the ordered list of fields the assistant's own
    previous message asked the employee for - it lets the model
    correctly interpret short, unlabeled replies like "no yes" as
    positional answers instead of losing that information.

    Never raises on malformed model output - falls back to an
    all-None, non-off-topic dict so the caller just re-asks for
    whatever is still missing.
    """

    client = get_client(token=token)

    asked_fields = asked_fields or []

    if asked_fields:
        asked_fields_block = "\n".join(
            f"{i + 1}. {f} ({FIELD_HINTS_AR.get(f, f)})"
            for i, f in enumerate(asked_fields)
        )
    else:
        asked_fields_block = "(none - this is the first message)"

    system_prompt = EXTRACTION_SYSTEM_PROMPT_TEMPLATE.format(
        asked_fields_block=asked_fields_block
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    response = client.chat_completion(
        messages=messages, max_tokens=600, temperature=0.0
    )

    raw = response.choices[0].message.content

    data = None

    try:
        cleaned = _strip_json_fences(raw)
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            data = parsed
    except (json.JSONDecodeError, TypeError):
        data = None

    if data is None:
        return _empty_extraction()

    result = {field: data.get(field) for field in REQUIRED_FIELDS}
    result["off_topic"] = bool(data.get("off_topic", False))

    return result


def apply_dataset_consistency_rules(data: dict) -> dict:
    """
    Deterministic (non-LLM) consistency rules matching the Telco
    dataset's own encoding - NOT invented values, just resolving
    categories that are logically implied once a parent field is
    known (e.g. no internet -> the internet-addon fields must read
    "No internet service", not be left blank or guessed by the LLM).
    """

    data = dict(data)

    if data.get("InternetService") == "No":
        for field in [
            "OnlineSecurity", "OnlineBackup", "DeviceProtection",
            "TechSupport", "StreamingTV", "StreamingMovies",
        ]:
            if not data.get(field):
                data[field] = "No internet service"

    if data.get("PhoneService") == "No" and not data.get("MultipleLines"):
        data["MultipleLines"] = "No phone service"

    if (
        data.get("MonthlyCharges") is not None
        and data.get("tenure") is not None
        and data.get("TotalCharges") is None
    ):
        # Clearly-labeled assumption, not an invented fact: employees
        # rarely know the exact lifetime total, so estimate it from
        # monthly charge x tenure (flagged to the employee in the UI).
        data["TotalCharges"] = round(
            data["MonthlyCharges"] * data["tenure"], 2
        )
        data["_total_charges_estimated"] = True

    return data


def get_missing_fields(data: dict) -> list:

    return [field for field in REQUIRED_FIELDS if data.get(field) is None]


def merge_customer_data(existing: dict, new: dict) -> dict:
    """
    Merge newly-extracted fields on top of what was already collected
    in earlier turns. New non-null values overwrite old ones (the
    employee correcting themselves); nulls never erase known data.
    """

    merged = dict(existing or {})

    for field in REQUIRED_FIELDS:
        value = new.get(field)
        if value is not None:
            merged[field] = value

    return merged
