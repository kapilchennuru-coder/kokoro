"""Background campaign runner: Kokoro TTS → Twilio Voice → persist real results."""

from __future__ import annotations

import os
import re
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

import db
import voice
from services import twilio_client
from services.telephony import check_telephony, resolve_mode

_lock = threading.Lock()
_running: dict[int, threading.Thread] = {}

PHONE_RE = re.compile(r"^\+?[\d]{7,15}$")
CALLING_HOURS_POLL_SEC = 20


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _notify(organization_id: int, user_id: int | None, message: str, level: str = "info"):
    if user_id is None:
        return
    db.add_notification(organization_id, user_id, message, level)


def _is_valid_phone(phone: str | None) -> bool:
    return bool(phone) and bool(PHONE_RE.match(phone.strip()))


def _within_calling_hours(settings: dict) -> bool:
    if str(settings.get("calling_hours_enabled", "false")).lower() != "true":
        return True
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(settings.get("timezone") or "America/New_York")
    except Exception:
        return True  # Fail open rather than block calling on a bad/missing tz database

    now_local = datetime.now(tz)
    days = {int(d) for d in (settings.get("calling_days") or "1,2,3,4,5").split(",") if d.strip().isdigit()}
    if now_local.isoweekday() not in days:
        return False

    def _parse_hm(value: str, fallback: str) -> tuple[int, int]:
        try:
            h, m = (value or fallback).split(":")
            return int(h), int(m)
        except (ValueError, AttributeError):
            fh, fm = fallback.split(":")
            return int(fh), int(fm)

    start_h, start_m = _parse_hm(settings.get("calling_hours_start"), "09:00")
    end_h, end_m = _parse_hm(settings.get("calling_hours_end"), "18:00")
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    now_minutes = now_local.hour * 60 + now_local.minute
    return start_minutes <= now_minutes < end_minutes


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
    # Accept {{name}}-style tokens too - a common typo/habit from other
    # templating systems that Python's str.format would otherwise treat as
    # a literal escaped brace and leave un-substituted in the spoken script.
    normalized = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"{\1}", template)
    try:
        return normalized.format(**values)
    except (KeyError, ValueError):
        # Fallback: simple replace for common tokens
        text = normalized
        for k, v in values.items():
            text = text.replace("{" + k + "}", str(v))
        return text


def _public_audio_url(call_id: int) -> str | None:
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base}/api/audio/{call_id}.wav" if base else None


def _public_status_callback_url() -> str | None:
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base}/api/webhooks/twilio/status" if base else None


def _poll_until_terminal(call_sid: str, mode: str, campaign_id: int) -> dict:
    """Twilio's calls.create() returns immediately with a non-final status;
    poll the REST API for the real outcome. (The status webhook also
    updates the DB independently when Twilio can reach this server - this
    poll is what lets the campaign loop itself progress reliably even when
    it can't, e.g. running on localhost with no public URL configured.)"""
    deadline = time.time() + twilio_client.MAX_POLL_SEC
    last = {"status": "error", "detail": "No response from Twilio."}
    while time.time() < deadline:
        campaign = db.get_campaign_by_id(campaign_id)
        if not campaign or campaign["status"] != "running":
            return {"status": "canceled", "detail": "Campaign paused/stopped while call was in progress."}
        last = twilio_client.fetch_status(call_sid, mode)
        if last.get("status") in twilio_client.TERMINAL_STATUSES:
            return last
        time.sleep(twilio_client.POLL_INTERVAL_SEC)
    return {"status": "timeout", "detail": "Timed out waiting for a final call status."}


def _run_campaign(campaign_id: int):
    campaign = db.get_campaign_by_id(campaign_id)
    if not campaign:
        return

    organization_id = campaign["organization_id"]
    notify_user_id = campaign.get("created_by")
    mode = resolve_mode(organization_id)
    telephony = check_telephony(organization_id)

    try:
        while True:
            campaign = db.get_campaign_by_id(campaign_id)
            if not campaign or campaign["status"] != "running":
                break

            settings = db.get_settings(organization_id)

            if not _within_calling_hours(settings):
                if campaign.get("agent_state") != "waiting_for_hours":
                    db.update_campaign(campaign_id, agent_state="waiting_for_hours")
                    _notify(organization_id, notify_user_id, f"Paused outside calling hours: {campaign['name']}", "info")
                time.sleep(CALLING_HOURS_POLL_SEC)
                continue

            pending = db.get_pending_campaign_contacts(campaign_id)
            if not pending:
                if db.has_scheduled_retries(campaign_id):
                    if campaign.get("agent_state") != "waiting_retry":
                        db.update_campaign(campaign_id, agent_state="waiting_retry")
                    time.sleep(CALLING_HOURS_POLL_SEC)
                    continue
                db.update_campaign(
                    campaign_id,
                    status="completed",
                    agent_state="idle",
                    completed_at=_iso(),
                    current_contact_id=None,
                    in_progress_calls=0,
                )
                _notify(organization_id, notify_user_id, f"Campaign completed: {campaign['name']}", "success")
                break

            contact_row = pending[0]
            contact_id = contact_row["contact_id"]
            contact = db.get_contact(organization_id, contact_id)
            if not contact:
                db.update_campaign_contact(campaign_id, contact_id, "failed")
                continue

            # Invalid numbers are never worth dialing or retrying - fail them
            # immediately rather than burning an AMI/TTS attempt on garbage.
            if not _is_valid_phone(contact.get("phone")):
                call_id = db.create_call(organization_id, campaign_id, contact_id, "", patient=contact)
                db.update_call(
                    call_id,
                    status="failed",
                    outcome="invalid_number",
                    detail="Phone number is not in a callable format.",
                    started_at=_iso(),
                    ended_at=_iso(),
                    duration_sec=0,
                )
                db.update_campaign_contact(campaign_id, contact_id, "failed", call_id)
                db.update_contact_calling(contact_id, "failed", campaign_id)
                campaign = db.get_campaign_by_id(campaign_id)
                db.update_campaign(
                    campaign_id,
                    completed_calls=(campaign["completed_calls"] or 0) + 1,
                    failed_calls=(campaign["failed_calls"] or 0) + 1,
                )
                continue

            script = _render_script(
                campaign.get("opening_message") or voice.DEFAULT_OPENING,
                contact,
            )

            call_id = db.create_call(organization_id, campaign_id, contact_id, script, patient=contact)
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
            simulated = False

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
                    # Persist the filename now (before dialing) so the public
                    # /api/audio/<call_id> route can already serve it once
                    # Twilio fetches the TwiML <Play> URL.
                    db.update_call(call_id, audio_filename=audio_name)
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

                    result = twilio_client.place_call(
                        to=contact["phone"],
                        script_text=script,
                        audio_url=_public_audio_url(call_id),
                        mode=mode,
                        status_callback_url=_public_status_callback_url(),
                    )
                    if result.get("sid"):
                        db.update_call(call_id, provider_call_sid=result["sid"])

                    if result["status"] == "error":
                        result_status = "error"
                        detail = result.get("detail") or result.get("raw") or ""
                    elif result.get("simulated"):
                        simulated = True
                        result_status = "simulated"
                        detail = "Simulated with Twilio test credentials - no real call was placed, no cost incurred."
                    else:
                        final = _poll_until_terminal(result["sid"], mode, campaign_id)
                        result_status = final.get("status") or "error"
                        detail = final.get("detail") or ""

                    db.append_call_event(
                        call_id,
                        {"ts": _iso(), "type": "result", "message": f"Result: {result_status}"},
                    )
                except Exception:
                    result_status = "error"
                    detail = "Unable to process this request right now."
                    db.append_call_event(call_id, {"ts": _iso(), "type": "error", "message": detail})
                    db.append_transcript(call_id, {"speaker": "system", "text": detail, "ts": _iso()})

            call_status, outcome = twilio_client.map_status(result_status, simulated=simulated)
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

            # Retry engine: no_answer/busy get another attempt later (up to
            # the configured max) instead of being counted as terminal.
            retry_max = int(settings.get("retry_max_attempts", 2) or 0)
            current_retry = contact_row.get("retry_count") or 0
            retryable = outcome in ("no_answer", "busy") and current_retry < retry_max

            if retryable:
                delay_key = "retry_delay_no_answer_ms" if outcome == "no_answer" else "retry_delay_busy_ms"
                delay_ms = int(settings.get(delay_key, 1800000) or 0)
                next_retry_at = (datetime.now(timezone.utc) + timedelta(milliseconds=delay_ms)).isoformat()
                db.schedule_retry(campaign_id, contact_id, current_retry + 1, next_retry_at)
                db.update_contact_calling(contact_id, call_status, campaign_id)
                db.append_call_event(
                    call_id,
                    {"ts": _iso(), "type": "retry_scheduled", "message": f"Retry {current_retry + 1}/{retry_max} scheduled"},
                )
                db.update_campaign(campaign_id, in_progress_calls=0, agent_state="waiting_retry")
            else:
                db.update_campaign_contact(campaign_id, contact_id, call_status, call_id)
                db.update_contact_calling(contact_id, call_status, campaign_id)

                # Refresh counters. Simulated (test-credential) calls get
                # their own bucket - never counted as a real answered call,
                # never counted as a real failure either. Busy is tracked
                # separately from a genuine failure so the UI can show them
                # as distinct outcomes rather than lumping both together.
                campaign = db.get_campaign_by_id(campaign_id)
                completed = (campaign["completed_calls"] or 0) + 1
                successful = campaign["successful_calls"] or 0
                no_answer = campaign["no_answer_calls"] or 0
                busy = campaign["busy_calls"] or 0
                failed = campaign["failed_calls"] or 0
                simulated_count = campaign["simulated_calls"] or 0
                if outcome == "simulated":
                    simulated_count += 1
                elif outcome == "answered":
                    successful += 1
                elif outcome == "no_answer":
                    no_answer += 1
                elif outcome == "busy":
                    busy += 1
                else:
                    failed += 1

                agent_state = "completed" if outcome in ("answered", "simulated") else "failed"
                db.update_campaign(
                    campaign_id,
                    completed_calls=completed,
                    successful_calls=successful,
                    no_answer_calls=no_answer,
                    busy_calls=busy,
                    failed_calls=failed,
                    simulated_calls=simulated_count,
                    in_progress_calls=0,
                    agent_state=agent_state,
                )

                if call_status == "completed" and outcome == "answered":
                    _notify(organization_id, notify_user_id, f"Call completed: {contact.get('name')}", "success")
                elif outcome == "simulated":
                    _notify(organization_id, notify_user_id, f"Simulated call (test mode): {contact.get('name')}", "info")

            # If telephony unavailable, fail campaign after first attempt (honest UX)
            if result_status == "telephony_unavailable":
                db.update_campaign(
                    campaign_id,
                    status="failed",
                    agent_state="failed",
                    error_message=detail,
                    completed_at=_iso(),
                )
                _notify(organization_id, notify_user_id, "Unable to start this campaign. Please try again later.", "error")
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
        _notify(organization_id, notify_user_id, "Campaign failed due to an internal error", "error")
    finally:
        with _lock:
            _running.pop(campaign_id, None)
