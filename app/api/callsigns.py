from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.transcribe.whisper import CALLSIGN_RE

router = APIRouter(prefix="/api/callsigns", tags=["callsigns"])

ADDRESS_ZIP_RE = re.compile(r"\s+\d{5}(?:-\d{4})?$")


def normalize_callsign(value: str) -> str:
    callsign = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if not callsign or not CALLSIGN_RE.fullmatch(callsign):
        raise ValueError("Invalid callsign")
    return callsign


def callsign_links(callsign: str, uls_url: str = "") -> list[dict[str, str]]:
    links = [{"label": "QRZ", "url": f"https://www.qrz.com/db/{callsign}"}]
    if uls_url:
        links.append({"label": "FCC ULS", "url": uls_url.replace("http://", "https://", 1)})
    else:
        links.append({"label": "FCC Search", "url": "https://wireless2.fcc.gov/UlsApp/UlsSearch/searchLicense.jsp"})
    return links


def _clean_location(line2: str) -> str:
    return ADDRESS_ZIP_RE.sub("", line2 or "").strip()


def fallback_callsign_details(callsign: str, message: str = "") -> dict[str, Any]:
    return {
        "callsign": callsign,
        "requested_callsign": callsign,
        "found": False,
        "status": "UNAVAILABLE" if message else "UNKNOWN",
        "source": "links",
        "message": message,
        "type": "",
        "name": "",
        "license_class": "",
        "previous_callsign": "",
        "trustee_name": "",
        "trustee_callsign": "",
        "location": "",
        "grid": "",
        "grant_date": "",
        "expires": "",
        "links": callsign_links(callsign),
    }


def details_from_callook(payload: dict[str, Any], requested_callsign: str) -> dict[str, Any]:
    status = str(payload.get("status") or "").upper()
    if status != "VALID":
        details = fallback_callsign_details(requested_callsign)
        details["status"] = status or "UNKNOWN"
        details["source"] = "callook.info"
        return details

    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    previous = payload.get("previous") if isinstance(payload.get("previous"), dict) else {}
    trustee = payload.get("trustee") if isinstance(payload.get("trustee"), dict) else {}
    address = payload.get("address") if isinstance(payload.get("address"), dict) else {}
    location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    other = payload.get("otherInfo") if isinstance(payload.get("otherInfo"), dict) else {}
    callsign = str(current.get("callsign") or requested_callsign).upper()

    return {
        "callsign": callsign,
        "requested_callsign": requested_callsign,
        "found": True,
        "status": status,
        "source": "callook.info",
        "message": "",
        "type": str(payload.get("type") or ""),
        "name": str(payload.get("name") or ""),
        "license_class": str(current.get("operClass") or current.get("class") or ""),
        "previous_callsign": str(previous.get("callsign") or "").upper(),
        "trustee_name": str(trustee.get("name") or ""),
        "trustee_callsign": str(trustee.get("callsign") or "").upper(),
        "location": _clean_location(str(address.get("line2") or "")),
        "grid": str(location.get("gridsquare") or ""),
        "grant_date": str(other.get("grantDate") or ""),
        "expires": str(other.get("expiryDate") or ""),
        "links": callsign_links(callsign, str(other.get("ulsUrl") or "")),
    }


@router.get("/{callsign}")
async def callsign_details(callsign: str) -> dict[str, Any]:
    try:
        normalized = normalize_callsign(callsign)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid callsign") from exc

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(f"https://callook.info/{normalized}/json")
            response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return fallback_callsign_details(normalized, "Lookup service unavailable. Use the links below.")

    return details_from_callook(payload, normalized)
