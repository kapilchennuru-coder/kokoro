"""Campaign CRUD and lifecycle controls."""

from __future__ import annotations

import db
from services import call_runner
from services.user_messages import sanitize_public_detail
from services.voice_catalog import get_voice


DEFAULT_OPENING = (
    "Hello {name}, this is a courtesy call from {hospital}. "
    "Our records show you have a pending balance of {balance_display}. "
    "Please contact the billing office at your earliest convenience. Thank you."
)


def start_calling_ready_patients(user_id: int) -> dict:
    """Create a simple campaign from all ready patients and start it."""
    ready = db.get_ready_contacts(user_id)
    if not ready:
        raise ValueError("There are no patients ready to call.")

    settings = db.get_settings(user_id)
    # Prefer latest list if available
    lists = db.get_contact_lists(user_id)
    list_id = lists[0]["id"] if lists else None

    data = {
        "name": f"Balance notifications {db.now_iso()[:10]}",
        "status": "ready",
        "list_id": list_id,
        "voice_id": settings.get("voice_id", "af_jessica"),
        "voice_speed": float(settings.get("voice_speed", 1.0)),
        "agent_name": settings.get("agent_name", "Outreach"),
        "opening_message": settings.get("opening_message") or DEFAULT_OPENING,
        "calling_mode": "sequential",
        "max_calls": len(ready),
        "delay_ms": int(settings.get("delay_ms", 2000)),
        "concurrency": 1,
        "total_contacts": len(ready),
    }
    campaign_id = db.create_campaign(user_id, data)
    db.link_campaign_contacts(campaign_id, [c["id"] for c in ready])
    return start_campaign(user_id, campaign_id)


def create_campaign(user_id: int, payload: dict) -> dict:
    list_id = payload.get("list_id")
    if not list_id:
        raise ValueError("Contact list is required")

    clist = db.get_contact_list(user_id, int(list_id))
    if not clist:
        raise ValueError("Contact list not found")

    contacts = db.get_valid_contacts_for_list(user_id, int(list_id))
    if not contacts:
        raise ValueError("No valid contacts in the selected list")

    max_calls = payload.get("max_calls")
    if max_calls:
        contacts = contacts[: int(max_calls)]

    settings = db.get_settings(user_id)
    data = {
        "name": (payload.get("name") or "").strip() or "Untitled Campaign",
        "status": "ready",
        "list_id": int(list_id),
        "voice_id": payload.get("voice_id") or settings.get("voice_id", "af_jessica"),
        "voice_speed": float(payload.get("voice_speed") or settings.get("voice_speed", 1.0)),
        "agent_name": payload.get("agent_name") or settings.get("agent_name", "Outreach"),
        "opening_message": payload.get("opening_message") or settings.get("opening_message") or DEFAULT_OPENING,
        "calling_mode": payload.get("calling_mode") or settings.get("calling_mode", "sequential"),
        "max_calls": int(max_calls) if max_calls else len(contacts),
        "delay_ms": int(payload.get("delay_ms") or settings.get("delay_ms", 2000)),
        "concurrency": int(payload.get("concurrency") or settings.get("concurrency", 1)),
        "total_contacts": len(contacts),
    }

    campaign_id = db.create_campaign(user_id, data)
    db.link_campaign_contacts(campaign_id, [c["id"] for c in contacts])
    campaign = db.get_campaign(user_id, campaign_id)
    campaign["voice"] = get_voice(campaign["voice_id"])
    campaign["ready_contacts"] = len(contacts)
    return campaign


def list_campaigns(user_id: int) -> list:
    campaigns = db.get_campaigns(user_id)
    for c in campaigns:
        c["voice"] = get_voice(c["voice_id"])
        total = c["total_contacts"] or 1
        c["progress"] = round((c["completed_calls"] / total) * 100, 1)
        c["success_rate"] = (
            round((c["successful_calls"] / c["completed_calls"]) * 100, 1)
            if c["completed_calls"]
            else 0
        )
    return campaigns


def get_campaign(user_id: int, campaign_id: int) -> dict | None:
    campaign = db.get_campaign(user_id, campaign_id)
    if not campaign:
        return None
    campaign["voice"] = get_voice(campaign["voice_id"])
    total = campaign["total_contacts"] or 1
    campaign["progress"] = round((campaign["completed_calls"] / total) * 100, 1)
    campaign["success_rate"] = (
        round((campaign["successful_calls"] / campaign["completed_calls"]) * 100, 1)
        if campaign["completed_calls"]
        else 0
    )
    if campaign.get("current_contact_id"):
        campaign["current_contact"] = db.get_contact(user_id, campaign["current_contact_id"])
    if campaign.get("current_call_id"):
        campaign["current_call"] = db.get_call(user_id, campaign["current_call_id"])
    if campaign.get("error_message"):
        campaign["error_message"] = sanitize_public_detail(campaign["error_message"])
    return campaign


def start_campaign(user_id: int, campaign_id: int) -> dict:
    campaign = db.get_campaign(user_id, campaign_id)
    if not campaign:
        raise ValueError("Campaign not found")
    if campaign["status"] not in ("ready", "paused", "failed"):
        raise ValueError(f"Cannot start campaign in status '{campaign['status']}'")

    db.update_campaign(
        campaign_id,
        status="running",
        agent_state="connecting",
        error_message=None,
        started_at=campaign.get("started_at") or db.now_iso(),
    )
    db.add_notification(user_id, f"Campaign started: {campaign['name']}", "success")
    call_runner.start(campaign_id)
    return get_campaign(user_id, campaign_id)


def pause_campaign(user_id: int, campaign_id: int) -> dict:
    campaign = db.get_campaign(user_id, campaign_id)
    if not campaign:
        raise ValueError("Campaign not found")
    if campaign["status"] != "running":
        raise ValueError("Only running campaigns can be paused")
    db.update_campaign(campaign_id, status="paused", agent_state="paused")
    db.add_notification(user_id, f"Campaign paused: {campaign['name']}", "info")
    return get_campaign(user_id, campaign_id)


def resume_campaign(user_id: int, campaign_id: int) -> dict:
    return start_campaign(user_id, campaign_id)


def stop_campaign(user_id: int, campaign_id: int) -> dict:
    campaign = db.get_campaign(user_id, campaign_id)
    if not campaign:
        raise ValueError("Campaign not found")
    if campaign["status"] not in ("running", "paused"):
        raise ValueError("Only running or paused campaigns can be stopped")
    db.update_campaign(
        campaign_id,
        status="completed",
        agent_state="idle",
        completed_at=db.now_iso(),
        in_progress_calls=0,
    )
    db.add_notification(user_id, f"Campaign stopped: {campaign['name']}", "info")
    return get_campaign(user_id, campaign_id)


def live_status(user_id: int, campaign_id: int) -> dict | None:
    return get_campaign(user_id, campaign_id)
