"""
Retention campaign catalog + economic ranking engine.

Campaigns are no longer hard-coded in prediction logic: they live in
app/config/campaigns.json (spec section 13) and are loaded once here.
Each campaign declares its own eligibility rule declaratively
(applies_if_field / applies_if_value / applies_if_max) instead of a
Python lambda, so non-engineers can edit the catalog without touching
code.

Every applicable campaign is scored by expected economic outcome
(Expected Net Benefit), NOT by success probability alone (spec section
14). If no campaign clears its own cost, the engine recommends
"Low-Cost Monitoring" instead of forcing an uneconomical campaign
(spec sections 15-16).
"""

import json
from pathlib import Path

CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "campaigns.json"
)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _CATALOG = json.load(f)["campaigns"]

# Backward-compatible alias (old engine.py exposed RETENTION_CAMPAIGNS as
# a dict of lambdas keyed by short name; here it's the raw JSON catalog
# list - kept under the same name for anything introspecting it).
RETENTION_CAMPAIGNS = _CATALOG


# ============================================
# Context-aware success probability adjustment
# ============================================
# The catalog's success_probability is a BASE scenario assumption
# (spec section 11 requires labeling assumptions as assumptions - we
# keep that base number transparent in campaigns.json). But using the
# same base for every customer flattens the ranking: whichever
# campaign has the single highest base rate (and applies to everyone,
# like the High-Touch call) wins almost every time regardless of the
# customer's actual situation.
#
# Instead, each campaign gets a small, explicit, capped adjustment
# based on whether it actually addresses THIS customer's churn
# drivers and behavioral segment - not a black-box number. This keeps
# variety in what gets recommended and keeps the "why" explainable.

# campaign_id -> substring(s) to look for in this customer's churn_drivers
_DRIVER_MATCH_KEYWORDS = {
    "RET_CONTRACT_UPGRADE": ["month-to-month", "contract"],
    "RET_TECH_SUPPORT_TRIAL": ["tech support", "no tech support"],
    "RET_SECURITY_TRIAL": ["online security", "no online security"],
    "RET_FIBER_SPEED_BOOST": ["fiber optic", "high monthly charges"],
    "RET_AUTOPAY_CREDIT": ["electronic check", "payment method"],
    "RET_NEW_CUSTOMER_DISCOUNT": ["short tenure", "new relationship", "tenure"],
}

DRIVER_MATCH_BONUS = 0.12  # campaign directly addresses a stated driver
SEGMENT_MATCH_BONUS = 0.05  # campaign targets this customer's segment
MAX_SUCCESS_PROBABILITY = 0.80
MIN_SUCCESS_PROBABILITY = 0.05


def _adjusted_success_probability(
    campaign: dict, churn_drivers: list, behavioral_segment: str
) -> tuple:
    """
    Returns (adjusted_probability, reasons) where reasons explains
    which adjustments were applied (for transparency in the UI/chat -
    never hidden math).
    """

    base = campaign["success_probability"]
    adjusted = base
    reasons = [f"Base scenario assumption: {base:.0%}"]

    keywords = _DRIVER_MATCH_KEYWORDS.get(campaign["campaign_id"], [])
    drivers_text = " | ".join(churn_drivers).lower()

    if keywords and any(kw in drivers_text for kw in keywords):
        adjusted += DRIVER_MATCH_BONUS
        reasons.append(
            f"+{DRIVER_MATCH_BONUS:.0%} - directly addresses a stated "
            "churn driver for this customer"
        )

    if behavioral_segment in campaign.get("target_segments", []):
        adjusted += SEGMENT_MATCH_BONUS
        reasons.append(
            f"+{SEGMENT_MATCH_BONUS:.0%} - matches this customer's "
            f"behavioral segment ({behavioral_segment})"
        )

    adjusted = max(MIN_SUCCESS_PROBABILITY, min(MAX_SUCCESS_PROBABILITY, adjusted))

    return round(adjusted, 4), reasons


def _campaign_applies(campaign: dict, customer_row) -> bool:

    field = campaign.get("applies_if_field")

    if field is None:
        return True

    if "applies_if_value" in campaign:
        return customer_row[field] == campaign["applies_if_value"]

    if "applies_if_max" in campaign:
        return customer_row[field] <= campaign["applies_if_max"]

    return True


def get_eligible_campaigns(customer_row) -> list:
    """Returns the raw catalog entries this customer is eligible for."""

    return [c for c in _CATALOG if _campaign_applies(c, customer_row)]


def _score_campaign(
    campaign: dict,
    expected_churn_loss: float,
    churn_drivers: list,
    behavioral_segment: str,
) -> dict:

    success_probability, probability_reasons = _adjusted_success_probability(
        campaign, churn_drivers, behavioral_segment
    )
    cost = campaign["cost"]

    expected_value_preserved = round(
        success_probability * expected_churn_loss, 2
    )
    expected_net_benefit = round(expected_value_preserved - cost, 2)
    expected_roi = (
        round(expected_net_benefit / cost, 2) if cost > 0 else None
    )

    return {
        "campaign_id": campaign["campaign_id"],
        "campaign": campaign["name"],
        "description": campaign["description"],
        "campaign_cost": cost,
        "expected_success_probability": success_probability,
        "success_probability_reasons": probability_reasons,
        "expected_value_preserved": expected_value_preserved,
        "expected_net_benefit": expected_net_benefit,
        "expected_roi": expected_roi,
    }


def select_retention_campaign(
    customer_row,
    expected_churn_loss: float,
    churn_drivers: list = None,
    behavioral_segment: str = "",
) -> dict:
    """
    Score every applicable retention campaign by expected economic
    benefit (not churn probability alone) and pick the best one.
    success_probability is adjusted per-customer based on whether the
    campaign addresses this customer's actual churn drivers/segment
    (see _adjusted_success_probability) - so different customers with
    different drivers genuinely get different recommendations, not
    the same catalog-wide highest-base-rate campaign every time.
    If no campaign has positive expected net benefit, recommend a
    low-cost / no-intervention strategy instead.
    """

    churn_drivers = churn_drivers or []

    eligible = get_eligible_campaigns(customer_row)

    candidates = [
        _score_campaign(c, expected_churn_loss, churn_drivers, behavioral_segment)
        for c in eligible
    ]

    if not candidates:
        fallback = next(
            c for c in _CATALOG if c["campaign_id"] == "RET_HIGH_TOUCH_CALL"
        )
        fallback_prob, fallback_reasons = _adjusted_success_probability(
            fallback, churn_drivers, behavioral_segment
        )
        candidates.append(
            {
                "campaign_id": fallback["campaign_id"],
                "campaign": fallback["name"],
                "description": fallback["description"],
                "campaign_cost": fallback["cost"],
                "expected_success_probability": fallback_prob,
                "success_probability_reasons": fallback_reasons,
                "expected_value_preserved": round(
                    fallback_prob * expected_churn_loss, 2
                ),
                "expected_net_benefit": None,
                "expected_roi": None,
            }
        )

    best = max(
        candidates,
        key=lambda x: (
            x["expected_net_benefit"]
            if x["expected_net_benefit"] is not None
            else -1e9
        ),
    )

    other_candidates = [
        c for c in candidates if c["campaign"] != best["campaign"]
    ]

    if (
        best["expected_net_benefit"] is not None
        and best["expected_net_benefit"] <= 0
    ):
        return {
            "campaign": "Low-Cost Monitoring (No Paid Campaign)",
            "description": (
                "No scenario campaign justifies its cost against the "
                "expected churn loss for this customer. Recommend "
                "low-cost monitoring / a courtesy check-in instead of "
                "a paid campaign."
            ),
            "campaign_cost": 0.0,
            "expected_success_probability": None,
            "expected_value_preserved": None,
            "expected_net_benefit": 0.0,
            "expected_roi": None,
            "other_candidates_considered": candidates,
        }

    result = dict(best)
    result["other_candidates_considered"] = other_candidates

    return result


def compare_campaigns(campaign_a: dict, campaign_b: dict) -> dict:
    """
    What-if / campaign comparison helper (spec section 21): compares
    two already-scored campaign dicts (as returned by
    select_retention_campaign / _score_campaign) purely on their own
    numbers - never invents new figures.
    """

    def net_benefit(c):
        return (
            c.get("expected_net_benefit")
            if c.get("expected_net_benefit") is not None
            else float("-inf")
        )

    better = (
        campaign_a
        if net_benefit(campaign_a) >= net_benefit(campaign_b)
        else campaign_b
    )

    return {
        "campaign_a": campaign_a,
        "campaign_b": campaign_b,
        "recommended": better["campaign"],
        "reason": (
            "Selected based on higher Expected Net Benefit between the "
            "two scenarios."
        ),
    }
