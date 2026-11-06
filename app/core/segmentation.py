"""
Two segmentation layers, both returned together for every customer:

1. Value x Risk segment (existing, preserved as-is):
   High Value + High Risk / High Value + Low Risk /
   Low Value + High Risk / Low Value + Low Risk

2. Behavioral / commercial segment (new): a second, more actionable
   lens on top of Value x Risk, with EXPLICIT eligibility rules per
   segment (never a blind/random assignment). Evaluated top-down in
   priority order; the first matching rule wins.

   "Service Recovery" is intentionally NOT implemented: it requires
   actual complaint/service-ticket data, which does not exist in this
   dataset. Fabricating it from churn probability alone would violate
   the "do not invent data" rule, so it's left out until real
   complaint data is wired in as a future enhancement).
"""

import numpy as np
import pandas as pd

from app.core.model_artifact import VALUE_CUTOFF


# ============================================
# 1. Value x Risk Segmentation (preserved)
# ============================================

def assign_value_risk_segment(
    customer_df: pd.DataFrame, churn_probability
) -> pd.DataFrame:

    result = customer_df.copy()

    result["EstimatedCustomerValue"] = np.where(
        result["TotalCharges"] > 0,
        result["MonthlyCharges"] * result["tenure"],
        0,
    )

    result["ValueBand"] = np.where(
        result["EstimatedCustomerValue"] >= VALUE_CUTOFF,
        "High Value",
        "Low Value",
    )

    # NOTE: this is a SEPARATE, coarser binary split (single 0.60 cutoff)
    # used only to build the Value x Risk segment below. It is
    # intentionally named differently from the 4-tier `Risk_Band`
    # produced by churn_engine.py (Low/Medium/High/Critical at
    # 0.25/0.50/0.75) to avoid the two being confused with each other -
    # they answer different questions and must not be swapped.
    result["ValueRiskLevel"] = np.where(
        churn_probability >= 0.60, "High Risk", "Low Risk"
    )

    conditions = [
        (
            (result["ValueBand"] == "High Value")
            & (result["ValueRiskLevel"] == "High Risk")
        ),
        (
            (result["ValueBand"] == "High Value")
            & (result["ValueRiskLevel"] == "Low Risk")
        ),
        (
            (result["ValueBand"] == "Low Value")
            & (result["ValueRiskLevel"] == "High Risk")
        ),
        (
            (result["ValueBand"] == "Low Value")
            & (result["ValueRiskLevel"] == "Low Risk")
        ),
    ]

    choices = [
        "High Value + High Risk",
        "High Value + Low Risk",
        "Low Value + High Risk",
        "Low Value + Low Risk",
    ]

    result["ValueRiskSegment"] = np.select(
        conditions, choices, default="Unassigned"
    )

    return result


# ============================================
# 2. Behavioral / Commercial Segmentation (new)
# ============================================
# Each function below IS the eligibility rule for that segment - no
# blind assignment. `assign_behavioral_segment` evaluates them in a
# fixed priority order and returns the first match, so a customer that
# could technically satisfy more than one rule still gets a single,
# well-defined label (most business-critical rule first).

def _is_service_gap(customer_row, missing_services, risk_band) -> bool:
    """Missing a service that is a known churn driver, while at
    elevated risk."""
    gap_services = {"Tech Support", "Online Security"}
    has_relevant_gap = bool(gap_services.intersection(missing_services))
    return has_relevant_gap and risk_band in ("High Risk", "Critical Risk")


def _is_new_and_fragile(tenure, risk_band) -> bool:
    return tenure <= 12 and risk_band in ("High Risk", "Critical Risk")


def _is_price_sensitive(customer_row, risk_band) -> bool:
    return (
        customer_row["Contract"] == "Month-to-month"
        and customer_row["MonthlyCharges"] > 70.35
        and risk_band in ("Medium Risk", "High Risk", "Critical Risk")
    )


def _is_high_value_at_risk(value_band, risk_band) -> bool:
    return value_band == "High Value" and risk_band in (
        "High Risk",
        "Critical Risk",
    )


def _is_loyal_underpenetrated(tenure, risk_band, missing_services) -> bool:
    return (
        tenure >= 24
        and risk_band in ("Low Risk", "Medium Risk")
        and len(missing_services) >= 2
    )


def _is_high_value_loyal(value_band, tenure, risk_band) -> bool:
    return (
        value_band == "High Value"
        and tenure >= 24
        and risk_band in ("Low Risk", "Medium Risk")
    )


def _is_cross_sell_opportunity(risk_band, missing_services) -> bool:
    return risk_band in ("Low Risk", "Medium Risk") and len(
        missing_services
    ) >= 1


def _is_low_value_high_risk(value_band, risk_band) -> bool:
    return value_band == "Low Value" and risk_band in (
        "High Risk",
        "Critical Risk",
    )


def _is_stable_low_value(value_band, risk_band) -> bool:
    return value_band == "Low Value" and risk_band in (
        "Low Risk",
        "Medium Risk",
    )


def assign_behavioral_segment(
    customer_row,
    value_band: str,
    risk_band: str,
    missing_services: list,
) -> dict:
    """
    Returns {"segment": <name>, "reason": <why this rule matched>}.
    Evaluated top-down; first matching rule wins. If nothing matches,
    returns "Unclassified" rather than guessing.
    """

    tenure = customer_row["tenure"]

    rules = [
        (
            "High-Value At-Risk",
            _is_high_value_at_risk(value_band, risk_band),
            "High estimated customer value combined with elevated churn risk.",
        ),
        (
            "New & Fragile",
            _is_new_and_fragile(tenure, risk_band),
            "Short tenure (<=12 months) combined with elevated churn risk.",
        ),
        (
            "Service Gap",
            _is_service_gap(customer_row, missing_services, risk_band),
            "Missing a service linked to churn risk (Tech Support / "
            "Online Security) while at elevated risk.",
        ),
        (
            "Price-Sensitive",
            _is_price_sensitive(customer_row, risk_band),
            "Month-to-month contract with above-median monthly charges "
            "and elevated churn risk.",
        ),
        (
            "Loyal Underpenetrated",
            _is_loyal_underpenetrated(tenure, risk_band, missing_services),
            "Long tenure and low/medium risk, but multiple services not "
            "yet adopted - a cross-sell opportunity within a stable "
            "relationship.",
        ),
        (
            "High-Value Loyal",
            _is_high_value_loyal(value_band, tenure, risk_band),
            "High estimated value, established tenure (24+ months), and "
            "low/medium churn risk.",
        ),
        (
            "Cross-Sell Opportunity",
            _is_cross_sell_opportunity(risk_band, missing_services),
            "Low/medium churn risk with at least one missing service.",
        ),
        (
            "Low-Value High-Risk",
            _is_low_value_high_risk(value_band, risk_band),
            "Low estimated value combined with elevated churn risk - "
            "warrants low-cost intervention only.",
        ),
        (
            "Stable Low-Value",
            _is_stable_low_value(value_band, risk_band),
            "Low estimated value and low/medium churn risk - stable, "
            "no urgent action required.",
        ),
    ]

    for name, matched, reason in rules:
        if matched:
            return {"segment": name, "reason": reason}

    return {
        "segment": "Unclassified",
        "reason": "No behavioral segment rule matched this customer's profile.",
    }
