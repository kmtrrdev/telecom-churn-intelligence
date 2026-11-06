"""
Conversation / customer context (spec section 6): a small typed
wrapper around "everything the chatbot currently knows about the
customer being discussed", so follow-up questions ("ليه؟", "طب لو
رفض؟", "قارنلي الحملتين") never require the employee to repeat
customer information.

This does not replace Streamlit's own session_state (which is the
actual persistence layer in this app) - it just gives a single,
well-defined shape for what goes into that state, so the API layer
(FastAPI) or any future non-Streamlit frontend can carry the same
context.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CustomerContext:

    customer_id: Optional[str] = None
    customer_input: dict = field(default_factory=dict)  # CustomerInput-shaped
    analysis: Optional[dict] = None  # last analyze_customer() output
    employee_decisions: list = field(default_factory=list)
    # each item: {"ai_recommendation": ..., "employee_decision": ...,
    #             "reason": ..., "timestamp": ...}

    def has_customer(self) -> bool:
        return self.analysis is not None

    def record_decision(
        self, ai_recommendation: str, employee_decision: str, reason: str = ""
    ) -> None:
        from datetime import datetime, timezone

        self.employee_decisions.append(
            {
                "ai_recommendation": ai_recommendation,
                "employee_decision": employee_decision,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def summary_for_llm(self) -> dict:
        """
        What gets injected into the LLM's grounding context: the
        engine's own analysis, plus the employee's override history
        (if any) so follow-up questions like "طب انت وافقت على القرار
        بتاعي؟" can be answered too.
        """

        payload = dict(self.analysis or {})
        if self.employee_decisions:
            payload["employee_decisions"] = self.employee_decisions
        return payload
