"""
Customer profile derivation: current services, missing services, and
service adoption rate. Used both for display and as input signal to
the segmentation / campaign / upsell engines.
"""

import pandas as pd


SERVICE_MAP = {
    "OnlineSecurity": "Online Security",
    "OnlineBackup": "Online Backup",
    "DeviceProtection": "Device Protection",
    "TechSupport": "Tech Support",
    "StreamingTV": "Streaming TV",
    "StreamingMovies": "Streaming Movies",
}

OPTIONAL_SERVICE_COLUMNS = list(SERVICE_MAP.keys())


def get_customer_profile(customer_df: pd.DataFrame) -> pd.DataFrame:

    profile = customer_df.copy()

    def get_current_services(row):

        services = []

        if row["PhoneService"] == "Yes":
            services.append("Phone Service")

        if row["MultipleLines"] == "Yes":
            services.append("Multiple Lines")

        if row["InternetService"] in ["DSL", "Fiber optic"]:
            services.append(f"{row['InternetService']} Internet")

        for column, service_name in SERVICE_MAP.items():
            if row[column] == "Yes":
                services.append(service_name)

        return services

    def get_missing_services(row):

        missing = []

        for column, service_name in SERVICE_MAP.items():
            if row[column] == "No":
                missing.append(service_name)

        return missing

    profile["CurrentServices"] = profile.apply(get_current_services, axis=1)
    profile["MissingServices"] = profile.apply(get_missing_services, axis=1)

    profile["ActiveOptionalServices"] = (
        profile[OPTIONAL_SERVICE_COLUMNS].eq("Yes").sum(axis=1)
    )

    profile["ServiceAdoptionRate"] = profile["ActiveOptionalServices"] / len(
        OPTIONAL_SERVICE_COLUMNS
    )

    return profile
