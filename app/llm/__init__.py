"""
Backward-compatible facade: the original monolithic app/llm.py has been
split into app/llm/{prompts,formatting,conversation,parser}.py (PHASE 1
refactor). Everything that used to do `from app.llm import X` keeps
working unchanged via these re-exports.
"""

from app.llm.prompts import (  # noqa: F401
    SYSTEM_PROMPT,
    REQUIRED_FIELDS,
    FIELD_HINTS_AR,
    EXTRACTION_SYSTEM_PROMPT_TEMPLATE,
)
from app.llm.formatting import build_messages  # noqa: F401
from app.llm.conversation import (  # noqa: F401
    get_client,
    chat_about_customer,
    chat_about_dataset,
    MODEL_ID,
    MODEL_DISPLAY_NAME,
    HF_TOKEN,
)
from app.llm.parser import (  # noqa: F401
    extract_customer_data,
    apply_dataset_consistency_rules,
    get_missing_fields,
    merge_customer_data,
)
