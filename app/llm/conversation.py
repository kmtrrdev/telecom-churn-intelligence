"""
Chat layer on top of the Customer Intelligence Engine.

Uses a FREE LLM served through the Hugging Face Inference API
(huggingface_hub.InferenceClient -> chat_completion), so no OpenAI/
paid key is needed. The LLM never invents numbers: it only talks about
the structured `analysis` dict produced by
app.core.decision_engine.analyze_customer, which is injected into the
system prompt as grounding context.

Setup:
    pip install huggingface_hub
    export HF_TOKEN="hf_xxx"   # free token from https://huggingface.co/settings/tokens

Model:
    Defaults to "deepseek-ai/DeepSeek-V3-0324" via provider="auto".
    Override with the CHAT_MODEL_ID env var if needed.
"""

import os
import re
from huggingface_hub import InferenceClient

from app.llm.prompts import SYSTEM_PROMPT, DATASET_SYSTEM_PROMPT
from app.llm.formatting import build_messages  # noqa: F401 (re-export)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================
# Configuration
# ============================================

HF_TOKEN = os.environ.get("HF_TOKEN")

MODEL_ID = os.environ.get("CHAT_MODEL_ID", "deepseek-ai/DeepSeek-V3-0324")

# Human-friendly label shown in the UI (kept separate from the raw
# HF model id, which is dev-facing wiring, not something an employee
# using the app needs to see).
MODEL_DISPLAY_NAME = os.environ.get(
    "CHAT_MODEL_DISPLAY_NAME", "DeepSeek V3"
)

_client = None
_client_key = None


def get_client(token: str = None):
    """
    Returns a cached InferenceClient routed through Hugging Face's
    Inference Providers (provider="auto" picks the fastest live
    backend for MODEL_ID). If `token` is passed explicitly it
    overrides the HF_TOKEN environment variable and forces a fresh
    client.
    """

    global _client, _client_key

    active_token = token or HF_TOKEN

    if not active_token:
        raise RuntimeError(
            "HF_TOKEN is not set. Create a free token at "
            "https://huggingface.co/settings/tokens and put it in a "
            "`.env` file next to the app as HF_TOKEN=hf_xxx."
        )

    cache_key = (MODEL_ID, active_token)

    if _client is None or _client_key != cache_key:
        _client = InferenceClient(
            model=MODEL_ID,
            token=active_token,
            provider="auto",
        )
        _client_key = cache_key

    return _client


# ============================================
# Output cleanup
# ============================================
# Stray script/token leakage guard: some free Inference Providers
# occasionally mis-render the chat template and leak fragments (CJK
# text, literal "user"/"assistant" role words) into the visible
# answer. We explicitly forbid this in the prompt above, and also
# strip it defensively as a safety net below.

_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]+"
)

_LEAKED_ROLE_TOKEN_PATTERN = re.compile(
    r"\b(user|assistant|system)\b\s*:?", re.IGNORECASE
)

# Some providers occasionally route to a reasoning-style variant that
# wraps its scratch thinking in <think>...</think> before the real
# answer. We never want that leaking into the chat UI.
_THINK_BLOCK_PATTERN = re.compile(
    r"<think>.*?</think>", re.IGNORECASE | re.DOTALL
)


def _clean_llm_output(text: str) -> str:

    if not text:
        return text

    cleaned = _THINK_BLOCK_PATTERN.sub("", text)
    cleaned = _CJK_PATTERN.sub("", cleaned)
    cleaned = _LEAKED_ROLE_TOKEN_PATTERN.sub("", cleaned)

    # Tidy up punctuation artifacts left behind by the removals above
    # (e.g. ".، " where the Chinese fragment used to sit).
    cleaned = re.sub(r"[.,،]\s*[.,،]", ".", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,،])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


# ============================================
# Public API - Chat about an existing analysis
# ============================================

def chat_about_customer(
    analysis: dict,
    question: str,
    history=None,
    token: str = None,
) -> str:
    """
    Ask the free HF-hosted LLM a question about a single customer's
    churn analysis. Returns the assistant's text reply.

    IMPORTANT: the LLM only explains the numbers in `analysis`
    (produced deterministically by
    app.core.decision_engine.analyze_customer). It never recomputes
    churn probability, financial figures, or recommendations itself.
    """

    client = get_client(token=token)

    messages = build_messages(
        analysis=analysis, question=question, history=history
    )

    response = client.chat_completion(
        messages=messages, max_tokens=900, temperature=0.4
    )

    raw_answer = response.choices[0].message.content

    return _clean_llm_output(raw_answer)


def chat_about_dataset(context: dict, question: str, history=None, token: str = None) -> str:
    """Answer a question grounded in the active uploaded dataset summary."""
    import json

    client = get_client(token=token)
    messages = [{
        "role": "system",
        "content": DATASET_SYSTEM_PROMPT + "\n\nCurrent uploaded dataset context:\n" + json.dumps(context, ensure_ascii=False, indent=2),
    }]
    if history:
        for turn in history:
            messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": question})
    response = client.chat_completion(messages=messages, max_tokens=900, temperature=0.3)
    return _clean_llm_output(response.choices[0].message.content)
