"""
Churn prediction: runs the production model on a raw customer row,
applies the validated production decision threshold, and assigns a
business-readable risk band. This is the ML source of truth — the LLM
layer never predicts churn itself.
"""

import numpy as np
import pandas as pd

from app.core.model_artifact import (
    MODEL,
    DECISION_THRESHOLD,
    engineer_model_features,
)


def predict_customer(customer_df: pd.DataFrame) -> pd.DataFrame:

    customer_df = customer_df.copy()

    # ========================================
    # Generate churn probability
    # ========================================

    model_input = engineer_model_features(customer_df)

    churn_probability = MODEL.predict_proba(model_input)[:, 1]

    # ========================================
    # Apply production threshold
    # ========================================

    churn_prediction = (churn_probability >= DECISION_THRESHOLD).astype(int)

    # ========================================
    # Risk band
    # ========================================

    risk_band = np.select(
        [
            churn_probability < 0.25,
            churn_probability < 0.50,
            churn_probability < 0.75,
        ],
        ["Low Risk", "Medium Risk", "High Risk"],
        default="Critical Risk",
    )

    # ========================================
    # Result
    # ========================================

    result = customer_df.copy()
    result["Churn_Probability"] = churn_probability
    result["Churn_Prediction"] = churn_prediction
    result["Churn_Decision"] = np.where(
        churn_prediction == 1, "CHURN", "NO CHURN"
    )
    result["Risk_Band"] = risk_band

    return result
