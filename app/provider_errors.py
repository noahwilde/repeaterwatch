from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProviderErrorDetails:
    message: str = ""
    code: str = ""
    type: str = ""


def provider_error_details(response: httpx.Response) -> ProviderErrorDetails:
    try:
        payload: Any = response.json()
    except ValueError:
        return ProviderErrorDetails(message=response.text.strip())
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return ProviderErrorDetails(
                message=str(error.get("message") or "").strip(),
                code=str(error.get("code") or "").strip(),
                type=str(error.get("type") or "").strip(),
            )
        if payload.get("message"):
            return ProviderErrorDetails(message=str(payload["message"]).strip())
    return ProviderErrorDetails()


def provider_error_text(response: httpx.Response) -> str:
    return provider_error_details(response).message


def provider_error_is_insufficient_quota(details: ProviderErrorDetails) -> bool:
    return "insufficient_quota" in {details.code.casefold(), details.type.casefold()}


def provider_retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    retry_after = response.headers.get("retry-after")
    if not retry_after:
        return None
    try:
        return max(1.0, float(retry_after))
    except ValueError:
        return None
