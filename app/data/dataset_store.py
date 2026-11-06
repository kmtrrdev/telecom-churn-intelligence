"""
Master customer dataset store (spec: "احفظ العميل اللي بيتبعت لوحده في
الـ CSV" — every customer analyzed one-by-one through the chat flow
gets appended here, so the same file also powers the CSV-upload
batch flow and the general dashboard).

Single file, CSV-backed (no DB dependency, consistent with
feedback_store.py's approach elsewhere in this app). Thread-safe via
a simple lock since FastAPI can serve concurrent requests.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATASET_PATH = DATA_DIR / "customers_dataset.csv"
CURRENT_UPLOAD_PATH = DATA_DIR / "current_upload.csv"

# Feature columns the analysis engine needs (mirrors CustomerInput,
# minus the derived TenureGroup).
FEATURE_COLUMNS = [
    "gender", "SeniorCitizen", "Partner", "Dependents", "tenure",
    "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity",
    "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV",
    "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod",
    "MonthlyCharges", "TotalCharges",
]

META_COLUMNS = ["customerID", "source", "added_at"]
ALL_COLUMNS = META_COLUMNS + FEATURE_COLUMNS

_lock = Lock()


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    df["MonthlyCharges"] = pd.to_numeric(df["MonthlyCharges"], errors="coerce")
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    df["tenure"] = pd.to_numeric(df["tenure"], errors="coerce")
    df["SeniorCitizen"] = pd.to_numeric(
        df["SeniorCitizen"], errors="coerce"
    ).fillna(0).astype(int)

    # TotalCharges missing/blank (common for brand-new customers in the
    # original dataset) -> approximate as MonthlyCharges x tenure,
    # same convention used by the chat-collection flow.
    est_mask = df["TotalCharges"].isna()
    df.loc[est_mask, "TotalCharges"] = (
        df.loc[est_mask, "MonthlyCharges"].fillna(0)
        * df.loc[est_mask, "tenure"].fillna(0)
    )
    df["tenure"] = df["tenure"].fillna(0).astype(int)
    df["MonthlyCharges"] = df["MonthlyCharges"].fillna(0.0)
    df["TotalCharges"] = df["TotalCharges"].fillna(0.0)
    return df


def _init_dataset() -> None:
    """
    Creates an empty master dataset file on first run. The project no
    longer ships the raw Kaggle CSV as a seed source: the dataset is
    populated purely at runtime, either one customer at a time via the
    chat flow (`append_single_customer`) or in bulk via CSV upload
    (`upsert_customers`).
    """
    if DATASET_PATH.exists():
        return
    pd.DataFrame(columns=ALL_COLUMNS).to_csv(DATASET_PATH, index=False)



def save_current_upload(df: pd.DataFrame) -> dict:
    """Persist the most recently uploaded CSV as the active dashboard dataset."""
    current = df.copy()
    if "customerID" not in current.columns:
        current["customerID"] = [f"ROW-{i + 1}" for i in range(len(current))]
    current = current.copy()
    current["customerID"] = current["customerID"].apply(
        lambda v: v if isinstance(v, str) and v.strip() else generate_customer_id()
    )
    for col in FEATURE_COLUMNS:
        if col not in current.columns:
            current[col] = None
    current = coerce_numeric(current)[["customerID"] + FEATURE_COLUMNS]
    with _lock:
        current.to_csv(CURRENT_UPLOAD_PATH, index=False)
    return {"rows": int(len(current)), "columns": list(current.columns)}


def load_current_upload() -> pd.DataFrame:
    """Load the active/latest uploaded CSV dataset, or an empty frame."""
    if not CURRENT_UPLOAD_PATH.exists():
        return pd.DataFrame(columns=["customerID"] + FEATURE_COLUMNS)
    with _lock:
        df = pd.read_csv(CURRENT_UPLOAD_PATH)
    for col in ["customerID"] + FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return coerce_numeric(df[["customerID"] + FEATURE_COLUMNS])


def clear_current_upload() -> None:
    """Remove the active/current uploaded CSV, if any, so the dashboard
    and dataset assistant go back to a clean "no file uploaded" state."""
    with _lock:
        if CURRENT_UPLOAD_PATH.exists():
            CURRENT_UPLOAD_PATH.unlink()


def current_upload_signature() -> str:
    if not CURRENT_UPLOAD_PATH.exists():
        return "empty"
    stat = CURRENT_UPLOAD_PATH.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def generate_customer_id() -> str:
    return f"MANUAL-{uuid.uuid4().hex[:8].upper()}"


def load_dataset() -> pd.DataFrame:
    with _lock:
        _init_dataset()
        df = pd.read_csv(DATASET_PATH)
    for col in ALL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[ALL_COLUMNS]


def dataset_stats() -> dict:
    df = load_dataset()
    return {
        "total_customers": int(len(df)),
        "manual_entries": int((df["source"] == "manual").sum()),
        "uploaded_entries": int((df["source"] == "csv_upload").sum()),
        "seed_entries": int((df["source"] == "seed").sum()),
    }


def upsert_customers(df: pd.DataFrame, source: str) -> dict:
    """
    Adds/updates rows in the master dataset (matched by customerID).
    Returns {"added": n, "updated": n}.
    """

    incoming = df.copy()
    if "customerID" not in incoming.columns:
        incoming["customerID"] = [generate_customer_id() for _ in range(len(incoming))]
    incoming["customerID"] = incoming["customerID"].apply(
        lambda v: v if isinstance(v, str) and v.strip() else generate_customer_id()
    )
    incoming["source"] = source
    incoming["added_at"] = datetime.now(timezone.utc).isoformat()
    for col in FEATURE_COLUMNS:
        if col not in incoming.columns:
            incoming[col] = None
    incoming = coerce_numeric(incoming)
    incoming = incoming[ALL_COLUMNS]

    with _lock:
        _init_dataset()
        current = pd.read_csv(DATASET_PATH)
        for col in ALL_COLUMNS:
            if col not in current.columns:
                current[col] = None
        current = current[ALL_COLUMNS]

        existing_ids = set(current["customerID"].astype(str))
        incoming_ids = set(incoming["customerID"].astype(str))
        updated = len(existing_ids & incoming_ids)
        added = len(incoming_ids - existing_ids)

        merged = pd.concat([current, incoming], ignore_index=True)
        merged["customerID"] = merged["customerID"].astype(str)
        merged = merged.drop_duplicates(subset="customerID", keep="last")
        merged.to_csv(DATASET_PATH, index=False)

    return {"added": added, "updated": updated}


def append_single_customer(record: dict, customer_id: str = None) -> dict:
    """
    Persists a single customer collected via the chat flow. Assigns a
    synthetic customerID if none was provided.
    """

    row = {col: record.get(col) for col in FEATURE_COLUMNS}
    row["customerID"] = customer_id or generate_customer_id()
    df = pd.DataFrame([row])
    upsert_customers(df, source="manual")
    return row


def dataset_file_signature() -> str:
    """
    Cheap change-detection key for the dashboard cache: mtime + size
    of the CSV, so the dashboard is only recomputed when the dataset
    actually changed (a new customer/CSV was saved), not on every
    request.
    """

    _init_dataset()
    stat = DATASET_PATH.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def get_customer_row(customer_id: str):
    df = load_dataset()
    match = df[df["customerID"].astype(str) == str(customer_id)]
    if match.empty:
        return None
    return match.iloc[0].to_dict()
