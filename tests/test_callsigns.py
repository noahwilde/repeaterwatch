from __future__ import annotations

import pytest

from app.api.callsigns import details_from_callook, normalize_callsign


def test_normalize_callsign_accepts_detected_format():
    assert normalize_callsign("k0abc") == "K0ABC"
    assert normalize_callsign("K0RPT") == "K0RPT"


def test_normalize_callsign_rejects_invalid_values():
    with pytest.raises(ValueError):
        normalize_callsign("not a callsign")


def test_details_from_callook_maps_public_license_fields():
    details = details_from_callook(
        {
            "status": "VALID",
            "type": "PERSON",
            "current": {"callsign": "K0ABC", "operClass": "GENERAL"},
            "previous": {"callsign": ""},
            "trustee": {"callsign": "", "name": ""},
            "name": "EXAMPLE, OPERATOR",
            "address": {"line2": "CEDAR RAPIDS, IA 52402"},
            "location": {"gridsquare": "EN41"},
            "otherInfo": {
                "grantDate": "01/02/2024",
                "expiryDate": "01/02/2034",
                "ulsUrl": "http://wireless2.fcc.gov/UlsApp/UlsSearch/license.jsp?licKey=123",
            },
        },
        "K0ABC",
    )

    assert details["found"] is True
    assert details["callsign"] == "K0ABC"
    assert details["name"] == "EXAMPLE, OPERATOR"
    assert details["license_class"] == "GENERAL"
    assert details["location"] == "CEDAR RAPIDS, IA"
    assert details["grid"] == "EN41"
    assert details["expires"] == "01/02/2034"
    assert details["links"][1]["url"].startswith("https://wireless2.fcc.gov")


def test_details_from_callook_handles_invalid_status_with_links():
    details = details_from_callook({"status": "INVALID"}, "BAD1")

    assert details["found"] is False
    assert details["status"] == "INVALID"
    assert details["links"][0]["label"] == "QRZ"
