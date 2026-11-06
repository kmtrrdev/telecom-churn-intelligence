"""
Runs the same PREDICT -> EXPLAIN -> QUANTIFY -> SEGMENT -> DECIDE ->
RECOMMEND pipeline (app.core.decision_engine.analyze_customer) over
many customers at once — either a freshly uploaded CSV or the
persisted master dataset — and rolls the per-customer results up into
aggregate dashboard numbers.

Kept separate from decision_engine.py: that module analyzes exactly
one customer and stays the single source of truth for the per-customer
numbers; this module never recomputes anything, it only loops and
aggregates.
"""

from collections import Counter

import pandas as pd

from app.core.decision_engine import analyze_customer
from app.data.dataset_store import FEATURE_COLUMNS


def analyze_dataframe(df: pd.DataFrame) -> dict:
    """
    Analyzes every row in `df` (must contain FEATURE_COLUMNS; an
    optional 'customerID' column is carried through). Rows that fail
    (bad/missing values) are skipped and reported in `errors` rather
    than aborting the whole batch.
    """

    results = []
    errors = []

    has_id = "customerID" in df.columns

    for i, (_, row) in enumerate(df.iterrows()):
        customer_id = str(row["customerID"]) if has_id and pd.notna(row.get("customerID")) else f"ROW-{i + 1}"
        try:
            row_df = pd.DataFrame([row[FEATURE_COLUMNS]])
            analysis = analyze_customer(row_df)
            analysis["customer_id"] = customer_id
            results.append(analysis)
        except Exception as e:  # noqa: BLE001 - keep the batch going
            errors.append({"customer_id": customer_id, "error": str(e)})

    return {"results": results, "errors": errors}


def build_dashboard(results: list) -> dict:
    """
    Aggregates a list of analyze_customer()-shaped dicts (each with a
    'customer_id' key added by analyze_dataframe) into dashboard-level
    KPIs, distributions, and ranked lists.
    """

    total = len(results)
    if total == 0:
        return {
            "total_customers": 0,
            "churn_count": 0,
            "churn_rate": 0.0,
            "avg_churn_probability": 0.0,
            "total_estimated_customer_value": 0.0,
            "total_expected_churn_loss": 0.0,
            "total_net_benefit_if_actioned": 0.0,
            "risk_band_distribution": {},
            "value_risk_segment_distribution": {},
            "behavioral_segment_distribution": {},
            "next_best_action_distribution": {},
            "top_risk_customers": [],
            "top_value_customers": [],
        }

    churn_count = 0
    prob_sum = 0.0
    value_sum = 0.0
    loss_sum = 0.0
    net_benefit_sum = 0.0
    retainable_val_sum = 0.0

    high_risk_count = 0
    med_risk_count = 0
    low_risk_count = 0

    contract_totals = Counter()
    contract_churns = Counter()
    drivers_counter = Counter()

    risk_band_counter = Counter()
    value_risk_counter = Counter()
    behavioral_counter = Counter()
    nba_counter = Counter()
    campaign_counter = Counter()

    ranked_risk = []
    ranked_value = []

    for r in results:
        pred = r["prediction"]
        seg = r["segmentation"]
        fin = r["financial"]
        action = r["recommended_action"]
        cust = r.get("customer", {})

        prob = pred["churn_probability"]
        is_churn = pred["decision"] == "CHURN"
        churn_count += int(is_churn)
        prob_sum += prob
        value_sum += seg["estimated_customer_value"]
        loss_sum += fin["expected_churn_loss"] if is_churn else 0.0

        if prob >= 0.5:
            high_risk_count += 1
        elif prob >= 0.35:
            med_risk_count += 1
        else:
            low_risk_count += 1

        contract_type = cust.get("contract") or cust.get("Contract") or "Month-to-month"
        contract_totals[contract_type] += 1
        if is_churn:
            contract_churns[contract_type] += 1

        for driver in r.get("churn_drivers", []):
            drivers_counter[driver] += 1

        retainable_val_sum += seg["estimated_customer_value"] if is_churn else 0.0

        camp = action.get("campaign") or {}
        act_type = action.get("type", "RETENTION")
        if isinstance(camp, dict):
            if act_type == "GROWTH" and camp.get("Service"):
                cname = f"Upsell: {camp['Service']}"
            else:
                cname = camp.get("campaign") or camp.get("name") or "Standard Retention Offer"
        elif isinstance(camp, str):
            cname = camp
        else:
            cname = "Low-Cost Monitoring"
        campaign_counter[cname] += 1

        net_benefit_sum += (camp.get("expected_net_benefit") if isinstance(camp, dict) and camp.get("expected_net_benefit") is not None else 0) or 0

        risk_band_counter[pred["risk_band"]] += 1
        value_risk_counter[seg["value_risk_segment"]] += 1
        behavioral_counter[seg["behavioral_segment"]] += 1
        nba_counter[r.get("next_best_action", "—")] += 1

        ranked_risk.append({
            "customer_id": r["customer_id"],
            "churn_probability": pred["churn_probability"],
            "risk_band": pred["risk_band"],
            "value_risk_segment": seg["value_risk_segment"],
            "behavioral_segment": seg["behavioral_segment"],
            "estimated_customer_value": seg["estimated_customer_value"],
            "expected_churn_loss": fin["expected_churn_loss"],
        })
        ranked_value.append(ranked_risk[-1])

    ranked_risk.sort(key=lambda x: x["churn_probability"], reverse=True)
    ranked_value.sort(key=lambda x: x["estimated_customer_value"], reverse=True)

    contract_churn_rates = {}
    for ctype, tot in contract_totals.items():
        contract_churn_rates[ctype] = round(contract_churns[ctype] / tot, 4) if tot > 0 else 0.0

    return {
        "total_customers": total,
        "churn_count": churn_count,
        "churn_rate": round(churn_count / total, 4),
        "avg_churn_probability": round(prob_sum / total, 4),
        "total_estimated_customer_value": round(value_sum, 2),
        "total_expected_churn_loss": round(loss_sum, 2),
        "total_retainable_value": round(retainable_val_sum, 2),
        "retainable_revenue_net_roi": round(net_benefit_sum, 2),
        "total_net_benefit_if_actioned": round(net_benefit_sum, 2),
        "risk_counts": {
            "HIGH": high_risk_count,
            "MEDIUM": med_risk_count,
            "LOW": low_risk_count
        },
        "churn_rate_by_contract": contract_churn_rates,
        "top_risk_factors": drivers_counter.most_common(5),
        "risk_band_distribution": dict(risk_band_counter),
        "value_risk_segment_distribution": dict(value_risk_counter),
        "behavioral_segment_distribution": dict(behavioral_counter),
        "next_best_action_distribution": dict(nba_counter),
        "campaign_distribution": dict(campaign_counter),
        "top_risk_customers": ranked_risk[:15],
        "top_value_customers": ranked_value[:15],
    }


def build_dataset_chat_context(df: pd.DataFrame, results: list) -> dict:
    """Build a compact, deterministic summary for the dataset assistant."""
    context = {
        "rows": int(len(df)),
        "columns": [c for c in df.columns],
    }
    if df.empty:
        return context

    # Raw-data summaries
    numeric = {}
    for col in ["tenure", "MonthlyCharges", "TotalCharges"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if not s.empty:
                numeric[col] = {
                    "average": round(float(s.mean()), 2),
                    "min": round(float(s.min()), 2),
                    "max": round(float(s.max()), 2),
                }
    context["numeric_summary"] = numeric

    categorical = {}
    for col in ["gender", "InternetService", "Contract", "PaymentMethod", "SeniorCitizen", "Partner", "Dependents"]:
        if col in df.columns:
            counts = df[col].fillna("Missing").astype(str).value_counts().to_dict()
            categorical[col] = {str(k): int(v) for k, v in counts.items()}
    context["category_counts"] = categorical

    if results:
        context["dashboard"] = build_dashboard(results)

        by_id = {str(r.get("customer_id")): r for r in results}
        rows = []
        for _, row in df.iterrows():
            cid = str(row.get("customerID"))
            r = by_id.get(cid)
            if not r:
                continue
            rows.append({
                "customer_id": cid,
                "tenure": row.get("tenure"),
                "InternetService": row.get("InternetService"),
                "Contract": row.get("Contract"),
                "PaymentMethod": row.get("PaymentMethod"),
                "MonthlyCharges": row.get("MonthlyCharges"),
                "TotalCharges": row.get("TotalCharges"),
                "churn_probability": r["prediction"]["churn_probability"],
                "risk_band": r["prediction"]["risk_band"],
                "value_risk_segment": r["segmentation"]["value_risk_segment"],
                "estimated_customer_value": r["segmentation"]["estimated_customer_value"],
                "expected_churn_loss": r["financial"]["expected_churn_loss"],
                "next_best_action": r.get("next_best_action"),
            })
        rows.sort(key=lambda x: x["churn_probability"], reverse=True)
        context["top_risk_customers"] = rows[:12]
        context["top_value_customers"] = sorted(
            rows, key=lambda x: x["estimated_customer_value"], reverse=True
        )[:12]

        # Useful grouped slices for natural-language questions.
        grouped = {}
        for col in ["InternetService", "Contract", "PaymentMethod", "SeniorCitizen"]:
            if col not in df.columns:
                continue
            buckets = {}
            base = df.copy()
            base["_cid"] = base["customerID"].astype(str)
            analysis_by_id = pd.DataFrame(rows)
            if analysis_by_id.empty:
                continue
            for key, grp in base.groupby(col, dropna=False):
                ids = set(grp["_cid"].tolist())
                ag = analysis_by_id[analysis_by_id["customer_id"].isin(ids)]
                if ag.empty:
                    continue
                churn_rate = float((ag["risk_band"].astype(str).str.contains("Risk")).mean()) if False else None
                # Use the deterministic decision field from raw results.
                id_to_result = {str(r.get("customer_id")): r for r in results}
                decisions = [id_to_result[cid]["prediction"]["decision"] for cid in ids if cid in id_to_result]
                probs = [id_to_result[cid]["prediction"]["churn_probability"] for cid in ids if cid in id_to_result]
                mvals = pd.to_numeric(grp["MonthlyCharges"], errors="coerce").dropna()
                buckets[str(key)] = {
                    "customers": int(len(grp)),
                    "churn_rate": round(sum(d == "CHURN" for d in decisions) / len(decisions), 4) if decisions else 0.0,
                    "avg_churn_probability": round(sum(probs) / len(probs), 4) if probs else 0.0,
                    "avg_monthly_charges": round(float(mvals.mean()), 2) if not mvals.empty else 0.0,
                }
            grouped[col] = buckets
        context["grouped_metrics"] = grouped

    return context
