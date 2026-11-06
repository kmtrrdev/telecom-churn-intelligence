import pandas as pd

from app.engine import analyze_customer


def test_engine_output(sample_customer):

    customer_df = pd.DataFrame(
        [sample_customer]
    )

    result = analyze_customer(
        customer_df
    )

    assert "prediction" in result
    assert "customer" in result
    assert "segmentation" in result
    assert "financial" in result
    assert "recommended_action" in result


def test_prediction_fields(sample_customer):

    customer_df = pd.DataFrame(
        [sample_customer]
    )

    result = analyze_customer(customer_df)

    assert result["prediction"]["decision"] in ("CHURN", "NO CHURN")
    assert 0.0 <= result["prediction"]["churn_probability"] <= 1.0
    assert result["prediction"]["risk_band"] in (
        "Low Risk", "Medium Risk", "High Risk", "Critical Risk"
    )
