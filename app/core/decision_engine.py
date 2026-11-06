"""
Top-level orchestrator: PREDICT -> EXPLAIN -> QUANTIFY -> SEGMENT ->
DECIDE -> RECOMMEND. This is the single entry point the API, the
Streamlit UI, and the LLM layer all call (`analyze_customer`). It
composes the individual engine modules but adds no new numbers of its
own beyond what they produce - it is glue, not a second source of
truth.

Output shape is intentionally backward-compatible with the original
monolithic engine.py: existing keys (prediction/customer/segmentation/
financial/churn_drivers/recommended_action) are unchanged, with new
keys added alongside them (segmentation.behavioral_segment,
data_quality, next_best_action) rather than breaking existing callers.
"""

import pandas as pd

from app.core.churn_engine import predict_customer
from app.core.customer_profile import get_customer_profile
from app.core.financial_engine import calculate_customer_economics
from app.core.segmentation import (
    assign_value_risk_segment,
    assign_behavioral_segment,
)
from app.core.shap_engine import get_churn_drivers
from app.core.campaign_engine import select_retention_campaign
from app.core.upsell_engine import score_upsell_opportunities


REQUIRED_CORE_FIELDS = [
    "gender",
    "SeniorCitizen",
    "Partner",
    "Dependents",
    "tenure",
    "PhoneService",
    "InternetService",
    "Contract",
    "PaymentMethod",
    "MonthlyCharges",
    "TotalCharges",
]


def assess_data_quality(customer_df: pd.DataFrame) -> str:
    """
    GOOD if every core field driving the prediction/financials is
    present and non-null; LIMITED otherwise. Never fabricates missing
    data - just flags reduced confidence to the employee.
    """

    row = customer_df.iloc[0]

    for field in REQUIRED_CORE_FIELDS:
        if field not in row or pd.isna(row[field]):
            return "LIMITED"

    return "GOOD"


def _select_next_best_action(
    decision: str,
    value_risk_segment: str,
    behavioral_segment: str,
    campaign_or_offer: dict,
) -> str:
    """
    Unified Next Best Action label (spec section 20), derived purely
    from what the retention/growth engines already decided - not a
    new decision layer with its own numbers.
    """

    if decision == "CHURN":
        if campaign_or_offer.get("campaign") == (
            "Low-Cost Monitoring (No Paid Campaign)"
        ):
            return "Low-cost retention"
        if campaign_or_offer.get("campaign_id") == "RET_CONTRACT_UPGRADE":
            return "Contract upgrade"
        if campaign_or_offer.get("campaign_id") == "RET_HIGH_TOUCH_CALL":
            return "High-touch retention"
        if campaign_or_offer.get("campaign_id") in (
            "RET_TECH_SUPPORT_TRIAL",
            "RET_SECURITY_TRIAL",
        ):
            return "Service trial"
        return "Low-cost retention"

    # NO CHURN
    if campaign_or_offer:
        return "Cross-sell" if behavioral_segment in (
            "Loyal Underpenetrated",
            "Cross-Sell Opportunity",
        ) else "Upsell"

    return "No action"


def analyze_customer(customer_df: pd.DataFrame) -> dict:

    customer_df = customer_df.copy()

    # ========================================
    # 0. Data quality
    # ========================================

    data_quality = assess_data_quality(customer_df)

    # ========================================
    # 1. Prediction
    # ========================================

    prediction = predict_customer(customer_df)

    churn_probability = float(prediction["Churn_Probability"].iloc[0])
    churn_prediction = int(prediction["Churn_Prediction"].iloc[0])
    decision = "CHURN" if churn_prediction == 1 else "NO CHURN"
    risk_band = prediction["Risk_Band"].iloc[0]

    # ========================================
    # 2. Profile
    # ========================================

    profile = get_customer_profile(customer_df)
    missing_services = profile["MissingServices"].iloc[0]

    # ========================================
    # 3. Financial
    # ========================================

    financial = calculate_customer_economics(customer_df, churn_probability)

    customer_value = float(financial["EstimatedCustomerValue"].iloc[0])
    future_revenue = float(financial["EstimatedFutureRevenue"].iloc[0])
    future_margin = float(financial["EstimatedFutureMargin"].iloc[0])
    expected_churn_loss = float(financial["ExpectedChurnLoss"].iloc[0])

    # ========================================
    # 4. Value x Risk + Behavioral segmentation
    # ========================================

    segmentation = assign_value_risk_segment(customer_df, churn_probability)

    value_band = segmentation["ValueBand"].iloc[0]
    value_risk_segment = segmentation["ValueRiskSegment"].iloc[0]

    behavioral = assign_behavioral_segment(
        customer_row=customer_df.iloc[0],
        value_band=value_band,
        risk_band=risk_band,  # 4-band Risk_Band from the churn engine
        missing_services=missing_services,
    )

    # ========================================
    # 5. Decision (Retention vs Growth)
    # ========================================

    churn_drivers = []

    if churn_prediction == 1:

        churn_drivers = get_churn_drivers(customer_df.iloc[0])

        best_campaign = select_retention_campaign(
            customer_df.iloc[0],
            expected_churn_loss,
            churn_drivers=churn_drivers,
            behavioral_segment=behavioral["segment"],
        )

        action = {
            "type": "RETENTION",
            "priority": (
                "HIGH"
                if value_risk_segment == "High Value + High Risk"
                else "MEDIUM"
            ),
            "campaign": best_campaign,
            "reason": "Customer requires churn prevention.",
        }

        next_best_action = _select_next_best_action(
            decision, value_risk_segment, behavioral["segment"], best_campaign
        )

    else:

        opportunities = score_upsell_opportunities(
            customer_df, churn_probability
        )

        best_offer = opportunities[0] if opportunities else None

        action = {
            "type": "GROWTH",
            "priority": "MEDIUM",
            "campaign": best_offer,
            "reason": (
                "Customer is not currently predicted to churn, so the "
                "focus is revenue expansion."
                if best_offer
                else "No high-confidence upsell opportunity identified."
            ),
        }

        next_best_action = _select_next_best_action(
            decision, value_risk_segment, behavioral["segment"], best_offer or {}
        )

    # ========================================
    # 6. Final response
    # ========================================

    return {
        "prediction": {
            "churn_probability": round(churn_probability, 4),
            "decision": decision,
            "risk_band": risk_band,
        },
        "customer": {
            "tenure": int(customer_df["tenure"].iloc[0]),
            "contract": customer_df["Contract"].iloc[0],
            "monthly_charges": float(
                customer_df["MonthlyCharges"].iloc[0]
            ),
            "current_services": profile["CurrentServices"].iloc[0],
            "missing_services": missing_services,
        },
        "segmentation": {
            "value_band": value_band,
            "value_risk_segment": value_risk_segment,
            "behavioral_segment": behavioral["segment"],
            "behavioral_segment_reason": behavioral["reason"],
            "estimated_customer_value": round(customer_value, 2),
        },
        "financial": {
            "estimated_future_revenue": round(future_revenue, 2),
            "estimated_future_margin": round(future_margin, 2),
            "expected_churn_loss": round(expected_churn_loss, 2),
            "assumptions": (
                "MonthlyCharges, margin_rate and campaign costs are "
                "current scenario assumptions, not fitted financial "
                "data."
            ),
        },
        "churn_drivers": churn_drivers,
        "recommended_action": action,
        "next_best_action": next_best_action,
        "data_quality": data_quality,
    }
