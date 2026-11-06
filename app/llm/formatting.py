"""
Builds the chat-completion message list (system + history + question)
for a grounded customer-analysis conversation. Split out from
conversation.py so it can be unit-tested without a live HF client.
"""

import json

from app.llm.prompts import SYSTEM_PROMPT


def build_messages(analysis: dict, question: str, history=None):

    context = json.dumps(analysis, ensure_ascii=False, indent=2)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\nCustomer analysis JSON:\n" + context,
        }
    ]

    if history:
        for turn in history:
            messages.append({"role": turn.role, "content": turn.content})

    messages.append({"role": "user", "content": question})

    return messages
