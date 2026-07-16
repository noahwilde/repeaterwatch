from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse


def base_url_allows_missing_api_key(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").casefold()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".local")
    return address.is_private or address.is_loopback or address.is_link_local


def openai_compatible_headers(base_url: str, api_key_env: str) -> dict[str, str]:
    api_key = os.getenv(api_key_env, "")
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    if base_url_allows_missing_api_key(base_url):
        return {}
    raise RuntimeError(f"{api_key_env} is not set")
