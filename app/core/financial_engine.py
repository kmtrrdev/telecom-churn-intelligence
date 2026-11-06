"""
Financial engine: estimated customer value, future revenue/margin
scenario, and expected churn loss. All figures are clearly scenario
assumptions (margin_rate, value_horizon_months come from the trained
artifact's finance_config, not measured company financial data).
"""

import numpy as np
import pandas as pd

from app.core.model_artifact import FINANCE_CONFIG


def calculate_customer_economics(
    customer_df: pd.DataFrame, churn_probability
) -> pd.DataFrame:

    result = customer_df.copy()

    horizon = FINANCE_CONFIG["value_horizon_months"]
    margin_rate = FINANCE_CONFIG["margin_rate"]

    # Current / historical value proxy
    result["EstimatedCustomerValue"] = np.where(
        result["TotalCharges"] > 0,
        result["MonthlyCharges"] * result["tenure"],
        0,
    )

    # Future revenue scenario
    result["EstimatedFutureRevenue"] = result["MonthlyCharges"] * horizon

    # Future margin scenario
    result["EstimatedFutureMargin"] = (
        result["EstimatedFutureRevenue"] * margin_rate
    )

    # Expected loss if customer churns
    result["ChurnProbability"] = churn_probability

    result["ExpectedChurnLoss"] = (
        result["ChurnProbability"] * result["EstimatedFutureMargin"]
    )

    return result
