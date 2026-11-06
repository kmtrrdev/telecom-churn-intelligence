"""
Backward-compatible facade over the refactored `app.core.*` modules.

The original monolithic engine.py has been split into
app/core/{model_artifact,churn_engine,customer_profile,financial_engine,
segmentation,shap_engine,campaign_engine,upsell_engine,decision_engine}.py
(see PHASE 1 refactor). This module re-exports the same public names so
that anything still doing `from app.engine import analyze_customer`
(main.py, tests, notebooks) keeps working unchanged.
"""

from app.core.model_artifact import (  # noqa: F401
    MODEL,
    MODEL_NAME,
    DECISION_THRESHOLD,
    VALUE_CUTOFF,
    FINANCE_CONFIG,
    engineer_model_features,
)
from app.core.churn_engine import predict_customer  # noqa: F401
from app.core.customer_profile import get_customer_profile  # noqa: F401
from app.core.financial_engine import (  # noqa: F401
    calculate_customer_economics,
)
from app.core.segmentation import (  # noqa: F401
    assign_value_risk_segment,
    assign_behavioral_segment,
)
from app.core.shap_engine import get_churn_drivers  # noqa: F401
from app.core.campaign_engine import (  # noqa: F401
    select_retention_campaign,
    compare_campaigns,
    RETENTION_CAMPAIGNS,
)
from app.core.upsell_engine import (  # noqa: F401
    score_upsell_opportunities,
    UPSELL_CONFIG,
)
from app.core.decision_engine import analyze_customer  # noqa: F401


if __name__ == "__main__":
    print("Production engine loaded successfully.")
