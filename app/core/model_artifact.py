"""
Production model artifact loading + inference-time feature engineering.

Loads the trained pipeline (model.pkl-equivalent, joblib format) exactly
as produced by `my-e-first-task.ipynb`, and reconstructs the derived
features the pipeline expects at inference time, using the SAME fixed
thresholds computed on the training data. This module is intentionally
side-effect-only at import time (loads the artifact once) so every other
engine module can import the already-loaded MODEL / THRESHOLD / config.
"""

import joblib
import pandas as pd
from pathlib import Path


# ============================================
# Load Production Artifact
# ============================================

import sys
import types

try:
    import imblearn
except ImportError:
    from importlib.machinery import ModuleSpec

    class DummyImblearnClass:
        def __init__(self, *args, **kwargs):
            pass
        def fit(self, *args, **kwargs):
            return self
        def fit_resample(self, *args, **kwargs):
            return args[0], args[1]
        def transform(self, X, *args, **kwargs):
            return X
        def fit_transform(self, X, *args, **kwargs):
            return X

    class DynamicImblearnModule(types.ModuleType):
        def __getattr__(self, name):
            if name == "Pipeline":
                from sklearn.pipeline import Pipeline
                return Pipeline
            return DummyImblearnClass

    class ImblearnFinder:
        def find_spec(self, fullname, path, target=None):
            if fullname == "imblearn" or fullname.startswith("imblearn."):
                return ModuleSpec(fullname, loader=self, is_package=True)
            return None

        def create_module(self, spec):
            if spec.name in sys.modules:
                return sys.modules[spec.name]
            mod = DynamicImblearnModule(spec.name)
            mod.__path__ = []
            sys.modules[spec.name] = mod
            return mod

        def exec_module(self, module):
            pass

    sys.meta_path.insert(0, ImblearnFinder())

import sklearn.compose._column_transformer
if not hasattr(sklearn.compose._column_transformer, "_RemainderColsList"):
    class _RemainderColsList(list):
        pass
    sklearn.compose._column_transformer._RemainderColsList = _RemainderColsList

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = BASE_DIR / "models" / "churn_model.joblib"

artifact = joblib.load(MODEL_PATH)

MODEL = artifact["model"]
MODEL_NAME = artifact["model_name"]
DECISION_THRESHOLD = artifact["decision_threshold"]
VALUE_CUTOFF = artifact["value_cutoff"]
FINANCE_CONFIG = artifact["finance_config"]

print(f"Loaded model: {MODEL_NAME}")
print(f"Decision threshold: {DECISION_THRESHOLD:.4f}")
print(f"Value cutoff: {VALUE_CUTOFF:.2f}")


# ============================================
# Model Feature Engineering
# ============================================
# The trained pipeline (see my-e-first-task.ipynb, "Feature Engineering"
# cell) expects several derived columns that do not exist on the raw
# CustomerInput schema. These must be reconstructed identically at
# inference time, using the same fixed thresholds that were computed
# once on the original Kaggle training CSV (not shipped with this
# project - only the resulting constants below are needed at runtime).

TENURE_BINS = [-1, 12, 24, 48, 72]

TENURE_LABELS = ["0–12 mo", "13–24 mo", "25–48 mo", "49+ mo"]

# Fixed threshold baked in at training time:
# df_ml["MonthlyCharges"].median() computed on the full training dataset
# (see my-e-first-task.ipynb, "Feature Engineering" cell). The raw
# training CSV itself is not shipped with the project at runtime -
# only this pre-computed constant is needed for inference.
HIGH_MONTHLY_CHARGE_THRESHOLD = 70.35

SERVICE_COLS_FOR_COUNT = [
    "PhoneService",
    "MultipleLines",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
]


def engineer_model_features(customer_df: pd.DataFrame) -> pd.DataFrame:

    df = customer_df.copy()

    df["TenureGroup"] = pd.cut(
        df["tenure"], bins=TENURE_BINS, labels=TENURE_LABELS
    )

    df["AvgMonthlySpend"] = df["TotalCharges"] / (df["tenure"] + 1)

    df["IsNewCustomer"] = (df["tenure"] <= 6).astype(int)

    df["HighMonthlyCharge"] = (
        df["MonthlyCharges"] > HIGH_MONTHLY_CHARGE_THRESHOLD
    ).astype(int)

    df["ServicesCount"] = df[SERVICE_COLS_FOR_COUNT].eq("Yes").sum(axis=1)

    df["AutoPayment"] = (
        df["PaymentMethod"].astype(str).str.contains("automatic").astype(int)
    )

    return df
