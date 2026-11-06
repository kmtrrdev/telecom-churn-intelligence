"""
Growth / Upsell engine for NO CHURN customers: scores each service the
customer does not currently have and returns the top candidates as
Next Best Offer material. Never recommends a service already owned,
and never forces an upsell if nothing scores well (caller decides the
"no high-confidence upsell" message - see decision_engine).
"""

from app.core.model_artifact import FINANCE_CONFIG

UPSELL_CONFIG = {
    "OnlineSecurity": {"name": "Online Security", "monthly_revenue": 8.0},
    "OnlineBackup": {"name": "Online Backup", "monthly_revenue": 7.0},
    "DeviceProtection": {
        "name": "Device Protection",
        "monthly_revenue": 9.0,
    },
    "TechSupport": {"name": "Tech Support", "monthly_revenue": 10.0},
    "StreamingTV": {"name": "Streaming TV", "monthly_revenue": 12.0},
    "StreamingMovies": {"name": "Streaming Movies", "monthly_revenue": 12.0},
}


def score_upsell_opportunities(customer_df, churn_probability) -> list:

    customer = customer_df.iloc[0]

    from app.core.model_artifact import VALUE_CUTOFF

    customer_value = customer["MonthlyCharges"] * customer["tenure"]

    high_value = customer_value >= VALUE_CUTOFF

    opportunities = []

    for column, config in UPSELL_CONFIG.items():

        # Already subscribed
        if customer[column] != "No":
            continue

        score = 20
        reasons = [f"Customer does not currently have {config['name']}."]

        # High-value customer
        if high_value:
            score += 20
            reasons.append(
                "Customer has relatively high estimated value."
            )

        # Stable customer
        if churn_probability < 0.30:
            score += 20
            reasons.append("Customer has relatively low churn risk.")

        # Established relationship
        if customer["tenure"] >= 24:
            score += 15
            reasons.append("Customer has an established relationship.")

        # Long-term contract
        if customer["Contract"] in ["One year", "Two year"]:
            score += 15
            reasons.append("Customer has a longer-term contract.")

        monthly_revenue = config["monthly_revenue"]
        annual_revenue = monthly_revenue * 12
        annual_margin = annual_revenue * FINANCE_CONFIG["margin_rate"]

        opportunities.append(
            {
                "Service": config["name"],
                "OpportunityScore": score,
                "Reason": " ".join(reasons),
                "EstimatedMonthlyRevenue": monthly_revenue,
                "EstimatedAnnualRevenue": annual_revenue,
                "EstimatedAnnualMargin": annual_margin,
            }
        )

    opportunities = sorted(
        opportunities,
        key=lambda x: (x["OpportunityScore"], x["EstimatedAnnualMargin"]),
        reverse=True,
    )

    return opportunities[:3]
