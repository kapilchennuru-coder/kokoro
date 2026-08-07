"""Background campaign runner: Kokoro TTS → Asterisk AMI → persist real results."""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

import ami_client
import db
import voice
from services.telephony import check_telephony

_lock = threading.Lock()
_running: dict[int, threading.Thread] = {}


def _iso():
    return datetime.now(timezone.utc).isoformat()


def start(campaign_id: int):
    with _lock:
        existing = _running.get(campaign_id)
        if existing and existing.is_alive():
            return
        t = threading.Thread(target=_run_campaign, args=(campaign_id,), daemon=True)
        _running[campaign_id] = t
        t.start()


def is_running(campaign_id: int) -> bool:
    t = _running.get(campaign_id)
    return bool(t and t.is_alive())


def _render_script(template: str, contact: dict) -> str:
    balance = contact.get("balance")
    if balance is None and contact.get("extras"):
        balance = contact["extras"].get("balance")
    try:
        balance_display = f"${float(balance):,.2f}" if balance is not None and balance != "" else "an outstanding amount"
    except (TypeError, ValueError):
        balance_display = contact.get("balance_display") or "an outstanding amount"
    hospital = contact.get("hospital") or contact.get("company") or "your healthcare provider"
    values = {
        "name": contact.get("name") or "there",
        "first_name": (contact.get("name") or "there").split()[0],
        "phone": contact.get("phone") or "",
        "balance": balance_display,
        "balance_display": balance_display,
        "hospital": hospital,
        "company": hospital,
    }
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        # Fallback: simple replace for common tokens
        text = template
        for k, v in values.items():
            text = text.replace("{" + k + "}", str(v))
        return text


def _map_outcome(status: str) -> tuple[str, str]:
    """Return (call_status, outcome) from AMI status."""
    mapping = {
        "answered": ("completed", "answered"),
        "no_answer": ("no_answer", "no_answer"),
        "rejected": ("failed", "busy"),
        "failed": ("failed", "failed"),
        "error": ("failed", "failed"),
        "unknown": ("failed", "failed"),
        "telephony_unavailable": ("failed", "failed"),
    }
    return mapping.get(status, ("failed", "failed"))


def _run_campaign(campaign_id: int):
    campaign = db.get_campaign_by_id(campaign_id)
    if not campaign:
        return

    user_id = campaign["user_id"]
    telephony = check_telephony()

    try:
        while True:
            campaign = db.get_campaign_by_id(campaign_id)
            if not campaign or campaign["status"] != "running":
                break

            pending = db.get_pending_campaign_contacts(campaign_id)
            if not pending:
                db.update_campaign(
                    campaign_id,
                    status="completed",
                    agent_state="idle",
                    completed_at=_iso(),
                    current_contact_id=None,
                    in_progress_calls=0,
                )
                db.add_notification(user_id, f"Campaign completed: {campaign['name']}", "success")
                break

            contact_row = pending[0]
            contact_id = contact_row["contact_id"]
            contact = db.get_contact(user_id, contact_id)
            if not contact:
                db.update_campaign_contact(campaign_id, contact_id, "failed")
                continue

            script = _render_script(
                campaign.get("opening_message") or voice.DEFAULT_OPENING,
                contact,
            )

            call_id = db.create_call(user_id, campaign_id, contact_id, script)
            db.update_campaign(
                campaign_id,
                current_contact_id=contact_id,
                current_call_id=call_id,
                agent_state="connecting",
                in_progress_calls=1,
            )
            db.update_campaign_contact(campaign_id, contact_id, "in_progress", call_id)
            db.update_contact_calling(contact_id, "in_progress", campaign_id)

            db.append_call_event(call_id, {"ts": _iso(), "type": "connecting", "message": "Connecting"})
            db.append_transcript(call_id, {"speaker": "system", "text": f"Connecting to {contact.get('name')}…", "ts": _iso()})

            started = time.time()
            result_status = "error"
            detail = ""
            audio_name = None

            # Telephony gate — do not fake success
            if not telephony.get("available"):
                result_status = "telephony_unavailable"
                detail = telephony.get("detail") or "Unable to start this campaign. Please try again later."
                db.update_campaign(campaign_id, agent_state="failed")
                db.append_call_event(call_id, {"ts": _iso(), "type": "error", "message": detail})
                db.append_transcript(call_id, {"speaker": "system", "text": detail, "ts": _iso()})
            else:
                try:
                    db.update_campaign(campaign_id, agent_state="speaking")
                    db.append_call_event(call_id, {"ts": _iso(), "type": "processing", "message": "Preparing message"})
                    audio_name = voice.generate_call_audio(
                        contact_id=str(contact_id),
                        script=script,
                        voice_name=campaign.get("voice_id") or "af_jessica",
                        speed=float(campaign.get("voice_speed") or 1.0),
                    )
                    db.append_transcript(
                        call_id,
                        {"speaker": "agent", "text": script, "ts": _iso()},
                    )
                    db.append_call_event(call_id, {"ts": _iso(), "type": "in_progress", "message": "In progress"})

                    # Re-check pause before placing call
                    campaign = db.get_campaign_by_id(campaign_id)
                    if not campaign or campaign["status"] != "running":
                        db.update_call(
                            call_id,
                            status="failed",
                            outcome="failed",
                            detail="Campaign paused/stopped before dial",
                            ended_at=_iso(),
                            duration_sec=int(time.time() - started),
                            audio_filename=audio_name,
                        )
                        db.update_campaign_contact(campaign_id, contact_id, "pending")
                        db.update_contact_calling(contact_id, "not_called", campaign_id)
                        break

                    result = ami_client.place_call(contact["phone"], audio_name)
                    result_status = result.get("status") or "error"
                    detail = result.get("detail") or result.get("raw") or ""
                    db.append_call_event(
                        call_id,
                        {"ts": _iso(), "type": "result", "message": f"Result: {result_status}"},
                    )
                except Exception:
                    result_status = "error"
                    detail = "Unable to process this request right now."
                    db.append_call_event(call_id, {"ts": _iso(), "type": "error", "message": detail})
                    db.append_transcript(call_id, {"speaker": "system", "text": detail, "ts": _iso()})

            call_status, outcome = _map_outcome(result_status)
            duration = int(time.time() - started)

            db.update_call(
                call_id,
                status=call_status,
                outcome=outcome,
                detail=detail[:2000] if detail else "",
                ended_at=_iso(),
                duration_sec=duration,
                audio_filename=audio_name,
            )
            db.update_campaign_contact(campaign_id, contact_id, call_status, call_id)
            db.update_contact_calling(contact_id, call_status, campaign_id)

            # Refresh counters
            campaign = db.get_campaign_by_id(campaign_id)
            completed = (campaign["completed_calls"] or 0) + 1
            successful = campaign["successful_calls"] or 0
            no_answer = campaign["no_answer_calls"] or 0
            failed = campaign["failed_calls"] or 0
            if outcome == "answered":
                successful += 1
            elif call_status == "no_answer":
                no_answer += 1
            else:
                failed += 1

            agent_state = "completed" if outcome == "answered" else "failed"
            db.update_campaign(
                campaign_id,
                completed_calls=completed,
                successful_calls=successful,
                no_answer_calls=no_answer,
                failed_calls=failed,
                in_progress_calls=0,
                agent_state=agent_state,
            )

            if call_status == "completed":
                db.add_notification(user_id, f"Call completed: {contact.get('name')}", "success")

            # If telephony unavailable, fail campaign after first attempt (honest UX)
            if result_status == "telephony_unavailable":
                db.update_campaign(
                    campaign_id,
                    status="failed",
                    agent_state="failed",
                    error_message=detail,
                    completed_at=_iso(),
                )
                db.add_notification(user_id, "Unable to start this campaign. Please try again later.", "error")
                break

            delay = max(int(campaign.get("delay_ms") or 2000), 0) / 1000.0
            # Honor pause during delay
            end_wait = time.time() + delay
            while time.time() < end_wait:
                campaign = db.get_campaign_by_id(campaign_id)
                if not campaign or campaign["status"] != "running":
                    break
                time.sleep(0.2)

    except Exception:
        db.update_campaign(
            campaign_id,
            status="failed",
            agent_state="failed",
            error_message=traceback.format_exc()[-500:],
            completed_at=_iso(),
            in_progress_calls=0,
        )
        db.add_notification(user_id, "Campaign failed due to an internal error", "error")
    finally:
        with _lock:
            _running.pop(campaign_id, None)
