"""
Local explanation for CHURN cases: a lightweight, rule-based stand-in
for SHAP local explanations, surfacing the factors most associated
with churn risk for this customer in business language.

This is a heuristic driver list, NOT causal proof and NOT true SHAP
values. Present these to employees as "contributed to the model's
prediction", never as "caused the customer to churn".
"""


def get_churn_drivers(customer_row) -> list:

    drivers = []

    if customer_row["Contract"] == "Month-to-month":
        drivers.append("Month-to-month contract (no lock-in)")

    if customer_row["TechSupport"] == "No":
        drivers.append("No Tech Support")

    if customer_row["OnlineSecurity"] == "No":
        drivers.append("No Online Security")

    if customer_row["tenure"] <= 12:
        drivers.append("Short tenure (new relationship)")

    if customer_row["InternetService"] == "Fiber optic":
        drivers.append("High-cost Fiber optic service")

    if customer_row["PaymentMethod"] == "Electronic check":
        drivers.append(
            "Electronic check payment (historically higher churn)"
        )

    if customer_row["PaperlessBilling"] == "Yes":
        drivers.append("Paperless billing")

    return drivers[:5]
