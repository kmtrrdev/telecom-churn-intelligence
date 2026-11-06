from pydantic import BaseModel, Field
from typing import Literal, Optional, List


class CustomerInput(BaseModel):

    gender: Literal["Male", "Female"]

    SeniorCitizen: int = Field(
        ge=0,
        le=1
    )

    Partner: Literal["Yes", "No"]

    Dependents: Literal["Yes", "No"]

    tenure: int = Field(
        ge=0
    )

    PhoneService: Literal["Yes", "No"]

    MultipleLines: str

    InternetService: Literal[
        "DSL",
        "Fiber optic",
        "No"
    ]

    OnlineSecurity: Literal[
        "Yes",
        "No",
        "No internet service"
    ]

    OnlineBackup: Literal[
        "Yes",
        "No",
        "No internet service"
    ]

    DeviceProtection: Literal[
        "Yes",
        "No",
        "No internet service"
    ]

    TechSupport: Literal[
        "Yes",
        "No",
        "No internet service"
    ]

    StreamingTV: Literal[
        "Yes",
        "No",
        "No internet service"
    ]

    StreamingMovies: Literal[
        "Yes",
        "No",
        "No internet service"
    ]

    Contract: Literal[
        "Month-to-month",
        "One year",
        "Two year"
    ]

    PaperlessBilling: Literal[
        "Yes",
        "No"
    ]

    PaymentMethod: str

    MonthlyCharges: float = Field(
        ge=0
    )

    TotalCharges: float = Field(
        ge=0
    )

    TenureGroup: Optional[str] = None


class ChatMessage(BaseModel):

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):

    customer: CustomerInput

    question: str = Field(
        min_length=1,
        description="User's question about this customer (e.g. 'why is this customer at risk?')"
    )

    history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="Previous turns in the conversation, if any"
    )
