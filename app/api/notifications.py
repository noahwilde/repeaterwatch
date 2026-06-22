from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_db, get_keyword_engine, get_notification_service
from app.models import KeywordRuleIn, PushSubscriptionIn, TestNotificationIn, TrafficAlertSettingsIn

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/vapid-public-key")
def vapid_public_key(request: Request) -> dict[str, str]:
    return {"public_key": get_notification_service(request).public_key}


@router.post("/subscriptions")
def save_subscription(payload: PushSubscriptionIn, request: Request) -> dict[str, int]:
    subscription_id = get_notification_service(request).save_subscription(payload.model_dump())
    return {"id": subscription_id}


@router.post("/test")
async def test_notification(payload: TestNotificationIn, request: Request) -> dict[str, int]:
    event_id = get_db(request).add_notification_event(
        {
            "rule_id": None,
            "repeater_id": None,
            "source_type": "test",
            "source_id": 0,
            "title": payload.title,
            "body": payload.body,
            "matched_text": "manual test",
        }
    )
    sent = await get_notification_service(request).send_event(event_id, payload.title, payload.body)
    return {"event_id": event_id, "sent": sent}


@router.get("/rules")
def list_rules(request: Request) -> list[dict]:
    return get_db(request).list_keyword_rules()


@router.get("/traffic-alerts")
def get_traffic_alerts(request: Request) -> dict[str, bool | str]:
    db = get_db(request)
    return {
        "enabled": db.traffic_alerts_enabled(),
        "suppress_phrases": db.traffic_alert_suppress_phrases_text(),
    }


@router.put("/traffic-alerts")
def update_traffic_alerts(payload: TrafficAlertSettingsIn, request: Request) -> dict[str, bool | str]:
    db = get_db(request)
    db.set_traffic_alerts_enabled(payload.enabled)
    db.set_traffic_alert_suppress_phrases(payload.suppress_phrases)
    return {
        "enabled": payload.enabled,
        "suppress_phrases": db.traffic_alert_suppress_phrases_text(),
    }


@router.post("/rules")
def create_rule(payload: KeywordRuleIn, request: Request) -> dict:
    rule_id = get_db(request).create_keyword_rule(payload.model_dump())
    rule = next((row for row in get_db(request).list_keyword_rules() if row["id"] == rule_id), None)
    return rule or {}


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, payload: KeywordRuleIn, request: Request) -> dict:
    db = get_db(request)
    if not any(row["id"] == rule_id for row in db.list_keyword_rules()):
        raise HTTPException(status_code=404, detail="Rule not found")
    db.update_keyword_rule(rule_id, payload.model_dump())
    return next((row for row in db.list_keyword_rules() if row["id"] == rule_id), {})


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, request: Request) -> dict[str, str]:
    get_db(request).delete_keyword_rule(rule_id)
    return {"status": "deleted"}


@router.delete("/events/{event_id}")
def delete_event(event_id: int, request: Request) -> dict[str, int | str]:
    db = get_db(request)
    if not db.get_notification_event(event_id):
        raise HTTPException(status_code=404, detail="Notification event not found")
    db.delete_notification_event(event_id)
    return {"status": "deleted", "id": event_id}


@router.delete("/events")
def clear_events(request: Request) -> dict[str, int | str]:
    deleted = get_db(request).clear_notification_events()
    return {"status": "cleared", "deleted": deleted}


@router.post("/match-test")
def match_test(payload: dict, request: Request) -> dict:
    text = str(payload.get("text", ""))
    repeater_id = payload.get("repeater_id")
    matches = get_keyword_engine(request).matching_rules("transcript", repeater_id, text)
    return {"matches": [{"rule_id": match.rule["id"], "matched_text": match.matched_text} for match in matches]}
