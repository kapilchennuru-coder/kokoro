# =============================================================
# AI Calling Dashboard — Flask JSON API
#
# Reuses Kokoro voice generation (voice.py). Telephony is Twilio Voice
# (services/twilio_client.py) - real outbound calls, test-credential
# mode for safe dry runs. React SPA is served from frontend/dist.
# =============================================================

from __future__ import annotations

import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

import db
import voice
from services import campaign_service, contact_service, demo_request_service, twilio_client
from services.rbac import client_ip, has_permission, require_permission, require_role
from services.telephony import check_telephony
from services.voice_catalog import list_agents, list_voices

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

ALLOWED_EXT = {".xlsx", ".xls", ".csv"}

db.init_db()


def api_error(message: str, status: int = 400, code: str | None = None, **extra):
    body = {"ok": False, "error": message, "error_code": code or "ERROR", **extra}
    return jsonify(body), status


def api_ok(data=None, **extra):
    body = {"ok": True, **(data if isinstance(data, dict) else {"data": data}), **extra}
    return jsonify(body)


def login_required_api(view):
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return api_error("Authentication required", 401)
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


# --------------- Auth ---------------

LOGIN_RATE_LIMIT = 5           # failed attempts
LOGIN_RATE_WINDOW_MIN = 15     # minutes


@app.post("/api/auth/login")
def api_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    ip = client_ip()
    ua = request.headers.get("User-Agent", "")[:255]

    if db.count_recent_login_failures(username, LOGIN_RATE_WINDOW_MIN) >= LOGIN_RATE_LIMIT:
        db.add_login_history(username, False, failure_reason="rate_limited", ip_address=ip, user_agent=ua)
        return api_error(
            "Too many failed login attempts. Please try again later.", 429, code="RATE_LIMITED"
        )

    user = db.get_user_by_username(username)
    # Same generic message whether the user doesn't exist or the password is
    # wrong - do not let login responses reveal which usernames are valid.
    if not user or not check_password_hash(user["password_hash"], password):
        db.add_login_history(
            username, False,
            user_id=user["id"] if user else None,
            failure_reason="invalid_credentials",
            ip_address=ip, user_agent=ua,
        )
        return api_error("Invalid username or password", 401, code="INVALID_CREDENTIALS")

    if user["status"] != "active":
        db.add_login_history(username, False, user_id=user["id"], failure_reason="account_inactive", ip_address=ip, user_agent=ua)
        return api_error("This account is deactivated. Contact an administrator.", 403, code="ACCOUNT_INACTIVE")

    session["user_id"] = user["id"]
    session["organization_id"] = user["organization_id"]
    session["client_name"] = user["client_name"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["login_history_id"] = db.add_login_history(
        username, True, user_id=user["id"], organization_id=user["organization_id"], ip_address=ip, user_agent=ua
    )
    db.touch_last_login(user["id"])
    db.add_audit_log("login", actor_id=user["id"], actor_username=username, organization_id=user["organization_id"],
                      entity="user", entity_id=user["id"], ip_address=ip)

    return api_ok({
        "user": {
            "id": user["id"],
            "username": user["username"],
            "client_name": user["client_name"],
            "email": user["email"],
            "role": user["role"],
        }
    })


@app.post("/api/auth/logout")
def api_logout():
    login_history_id = session.get("login_history_id")
    if login_history_id:
        db.mark_login_logout(login_history_id)
    if "user_id" in session:
        db.add_audit_log("logout", actor_id=session["user_id"], actor_username=session.get("username"),
                          organization_id=session.get("organization_id"), ip_address=client_ip())
    session.clear()
    return api_ok({"message": "Logged out"})


@app.get("/api/auth/me")
def api_me():
    if "user_id" not in session:
        return api_error("Not authenticated", 401)
    return api_ok({
        "user": {
            "id": session["user_id"],
            "username": session.get("username"),
            "client_name": session.get("client_name"),
            "role": session.get("role"),
        }
    })


# --------------- Dashboard ---------------

@app.get("/api/dashboard")
@login_required_api
def api_dashboard():
    organization_id = session["organization_id"]
    contacts = db.count_contacts(organization_id)
    active = db.get_active_campaign(organization_id)
    recent_calls = db.get_calls(organization_id, page=1, page_size=8)
    return api_ok({
        "kpis": {
            "total_contacts": contacts["total"],
            "contacts_ready": contacts["ready"],
            "calls_completed": contacts["completed"],
            "remaining": contacts["remaining"],
            "in_progress": contacts["in_progress"],
        },
        "active_campaign": active,
        "recent_calls": recent_calls.get("items", []),
        "notifications": db.get_notifications(session["user_id"], 10),
    })


# --------------- Contacts / Excel ---------------

@app.get("/api/contacts")
@require_permission("view_patients")
def api_contacts():
    uid = session["user_id"]
    result = contact_service.list_contacts(
        uid,
        list_id=int(request.args["list_id"]) if request.args.get("list_id") else None,
        search=request.args.get("search", ""),
        status=request.args.get("status", ""),
        validation=request.args.get("validation", ""),
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 25)),
        sort_by=request.args.get("sort_by", "id"),
        sort_dir=request.args.get("sort_dir", "asc"),
    )
    return api_ok(result)


@app.get("/api/contacts/<int:contact_id>")
@require_permission("view_patients")
def api_contact_detail(contact_id: int):
    contact = contact_service.get_contact(session["user_id"], contact_id)
    if not contact:
        return api_error("Patient not found", 404)
    return api_ok({"contact": contact, "patient": contact})


@app.put("/api/contacts/<int:contact_id>")
@require_permission("edit_patients")
def api_update_contact(contact_id: int):
    payload = request.get_json(silent=True) or {}
    data = {
        "name": payload.get("name"),
        "phone": payload.get("phone"),
        "balance": payload.get("balance"),
        "hospital": payload.get("hospital"),
    }
    contact = contact_service.update_contact(session["user_id"], contact_id, data)
    if not contact:
        return api_error("Patient not found", 404, code="NOT_FOUND")
    db.add_audit_log("patient_update", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="patient", entity_id=contact_id, metadata=data, ip_address=client_ip())
    return api_ok({"contact": contact, "patient": contact})


@app.delete("/api/contacts/<int:contact_id>")
@require_permission("delete_patients")
def api_delete_contact(contact_id: int):
    ok = contact_service.delete_contact(session["user_id"], contact_id)
    if not ok:
        return api_error("Patient not found", 404, code="NOT_FOUND")
    db.add_audit_log("patient_delete", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="patient", entity_id=contact_id, ip_address=client_ip())
    return api_ok({"deleted": True})


@app.delete("/api/contacts")
@require_permission("delete_patients")
def api_delete_contacts_bulk():
    payload = request.get_json(silent=True) or {}
    ids = [int(i) for i in payload.get("ids") or [] if str(i).isdigit()]
    if not ids:
        return api_error("No patients selected", 400, code="NO_SELECTION")
    deleted = contact_service.delete_contacts(session["user_id"], ids)
    db.add_audit_log("patient_bulk_delete", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="patient", metadata={"ids": ids, "deleted_count": deleted}, ip_address=client_ip())
    return api_ok({"deleted_count": deleted})


@app.post("/api/contacts")
@require_permission("import_patients")
def api_create_contact():
    payload = request.get_json(silent=True) or {}
    try:
        contact = contact_service.add_contact(session["user_id"], payload)
    except ValueError as exc:
        return api_error(str(exc))
    db.add_audit_log("patient_create", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="patient", entity_id=contact.get("id"), ip_address=client_ip())
    return api_ok({"contact": contact, "patient": contact})


@app.get("/api/contact-lists")
@require_permission("view_patients")
def api_contact_lists():
    return api_ok({"lists": contact_service.list_lists(session["user_id"])})


@app.post("/api/contacts/upload")
@require_permission("import_patients")
def api_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return api_error("Choose a file first")
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return api_error("Please upload an Excel file (.xlsx or .xls)")

    saved = os.path.join(UPLOAD_DIR, f"user{session['user_id']}_{filename}")
    file.save(saved)
    try:
        result = contact_service.stash_upload(session["user_id"], saved, filename)
    except ValueError as exc:
        return api_error(str(exc))
    except Exception:
        return api_error("Unable to read this file. Please check the Excel file and try again.")
    return api_ok(result)


@app.get("/api/contacts/upload/pending")
@require_permission("import_patients")
def api_pending_upload():
    pending = contact_service.get_pending(session["user_id"])
    if not pending:
        return api_ok({"pending": None})
    return api_ok({
        "pending": {
            "filename": pending["filename"],
            "columns": pending["columns"],
            "detected_mapping": pending["detected_mapping"],
            "row_count": pending["row_count"],
            "requires_mapping": pending.get("requires_mapping", True),
            "persisted": False,
        }
    })


@app.delete("/api/contacts/upload/pending")
@require_permission("import_patients")
def api_discard_pending():
    contact_service.cancel_pending(session["user_id"])
    return api_ok({"cancelled": True, "persisted": False})


@app.post("/api/contacts/upload/preview")
@require_permission("import_patients")
def api_preview_mapping():
    payload = request.get_json(silent=True) or {}
    mapping = payload.get("mapping") or {}
    try:
        result = contact_service.preview_with_mapping(session["user_id"], mapping)
    except ValueError as exc:
        return api_error(str(exc))
    except Exception:
        return api_error("Unable to prepare preview. Please try again.")
    return api_ok(result)


@app.post("/api/contacts/upload/confirm")
@require_permission("import_patients")
def api_confirm_import():
    payload = request.get_json(silent=True) or {}
    mapping = payload.get("mapping") or {}
    list_name = payload.get("list_name")
    try:
        result = contact_service.confirm_import(session["user_id"], mapping, list_name)
    except ValueError as exc:
        return api_error(str(exc))
    except Exception:
        return api_error("Unable to import records. Please try again.")
    db.add_audit_log("patient_import", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="contact_list", entity_id=result.get("list_id"),
                      metadata={"imported_count": result.get("imported_count"), "filename": result.get("filename")},
                      ip_address=client_ip())
    return api_ok(result)


@app.post("/api/contacts/upload/cancel")
@require_permission("import_patients")
def api_cancel_import():
    contact_service.cancel_pending(session["user_id"])
    return api_ok({"cancelled": True, "persisted": False})


# --------------- Demo requests (public marketing site) ---------------

@app.post("/api/demo-requests")
def api_create_demo_request():
    """Public, unauthenticated - the marketing site's Request a Demo form
    posts here directly. No session/org context: leads aren't tenant data."""
    payload = request.get_json(silent=True) or {}
    try:
        result = demo_request_service.submit(payload, client_ip())
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok(result)


@app.get("/api/demo-requests")
@require_permission("manage_leads")
def api_list_demo_requests():
    result = demo_request_service.list_requests(
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 25)),
        status=request.args.get("status", ""),
    )
    return api_ok(result)


@app.put("/api/demo-requests/<int:request_id>")
@require_permission("manage_leads")
def api_update_demo_request(request_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        updated = demo_request_service.update_status(
            request_id, payload.get("status"), payload.get("notes")
        )
    except ValueError as exc:
        return api_error(str(exc))
    if not updated:
        return api_error("Demo request not found", 404, code="NOT_FOUND")
    db.add_audit_log("demo_request_status_update", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="demo_request", entity_id=request_id,
                      metadata={"status": payload.get("status")}, ip_address=client_ip())
    return api_ok({"demo_request": updated})


# --------------- Campaigns ---------------

@app.get("/api/campaigns")
@login_required_api
def api_campaigns():
    return api_ok({"campaigns": campaign_service.list_campaigns(session["user_id"])})


@app.post("/api/campaigns")
@require_permission("create_campaign")
def api_create_campaign():
    payload = request.get_json(silent=True) or {}
    try:
        campaign = campaign_service.create_campaign(session["user_id"], payload)
    except ValueError as exc:
        return api_error(str(exc))
    except Exception as exc:
        return api_error(f"Could not create campaign: {exc}")
    db.add_audit_log("campaign_create", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="campaign", entity_id=campaign.get("id"), ip_address=client_ip())
    return api_ok({"campaign": campaign})


@app.get("/api/campaigns/<int:campaign_id>")
@login_required_api
def api_get_campaign(campaign_id: int):
    campaign = campaign_service.get_campaign(session["user_id"], campaign_id)
    if not campaign:
        return api_error("Campaign not found", 404)
    return api_ok({"campaign": campaign})


@app.get("/api/campaigns/<int:campaign_id>/live")
@login_required_api
def api_live_campaign(campaign_id: int):
    campaign = campaign_service.live_status(session["user_id"], campaign_id)
    if not campaign:
        return api_error("Campaign not found", 404)
    return api_ok({
        "campaign": campaign,
        "telephony": check_telephony(session["organization_id"]),
        "tts": voice.tts_available(),
    })


@app.post("/api/calling/start")
@require_permission("start_campaign")
def api_start_calling():
    try:
        campaign = campaign_service.start_calling_ready_patients(session["user_id"])
    except ValueError as exc:
        return api_error(str(exc))
    db.add_audit_log("campaign_start", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="campaign", entity_id=campaign.get("id"), ip_address=client_ip())
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/start")
@require_permission("start_campaign")
def api_start_campaign(campaign_id: int):
    try:
        campaign = campaign_service.start_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    db.add_audit_log("campaign_start", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="campaign", entity_id=campaign_id, ip_address=client_ip())
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/pause")
@require_permission("pause_campaign")
def api_pause_campaign(campaign_id: int):
    try:
        campaign = campaign_service.pause_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    db.add_audit_log("campaign_pause", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="campaign", entity_id=campaign_id, ip_address=client_ip())
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/resume")
@require_permission("start_campaign")
def api_resume_campaign(campaign_id: int):
    try:
        campaign = campaign_service.resume_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    db.add_audit_log("campaign_resume", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="campaign", entity_id=campaign_id, ip_address=client_ip())
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/stop")
@require_permission("stop_campaign")
def api_stop_campaign(campaign_id: int):
    try:
        campaign = campaign_service.stop_campaign(session["user_id"], campaign_id)
        db.add_audit_log("campaign_stop", actor_id=session["user_id"], actor_username=session.get("username"),
                                                    organization_id=session["organization_id"], entity="campaign", entity_id=campaign_id, ip_address=client_ip())
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok({"campaign": campaign})


# --------------- Calls ---------------

@app.get("/api/calls")
@require_permission("view_calls")
def api_calls():
    result = db.get_calls(
        session["organization_id"],
        search=request.args.get("search", ""),
        status=request.args.get("status", ""),
        outcome=request.args.get("outcome", ""),
        campaign_id=int(request.args["campaign_id"]) if request.args.get("campaign_id") else None,
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 25)),
    )
    return api_ok(result)


@app.get("/api/calls/<int:call_id>")
@require_permission("view_calls")
def api_call_detail(call_id: int):
    call = db.get_call(session["organization_id"], call_id)
    if not call:
        return api_error("Call not found", 404)
    return api_ok({"call": call})


# --------------- Settings / voices / health ---------------

@app.get("/api/voices")
@login_required_api
def api_voices():
    return api_ok({"voices": list_voices(), "agents": list_agents()})


@app.post("/api/voices/preview")
@require_permission("manage_voices")
def api_voice_preview():
    """Generate a short real Kokoro sample so admins can hear a voice before
    assigning it - no telephony involved, just TTS -> audio bytes."""
    import uuid
    from flask import Response

    payload = request.get_json(silent=True) or {}
    voice_id = payload.get("voice_id") or "af_jessica"
    speed = float(payload.get("speed") or 1.0)
    text = (payload.get("text") or "").strip() or (
        "Hello, this is a preview of the selected voice for your calling campaigns."
    )
    if len(text) > 400:
        return api_error("Preview text is too long (max 400 characters).", 400, code="TEXT_TOO_LONG")

    try:
        filename_no_ext = voice.generate_call_audio(
            contact_id=f"preview_{uuid.uuid4().hex[:8]}",
            script=text,
            voice_name=voice_id,
            speed=speed,
        )
    except Exception:
        return api_error("Unable to generate a voice preview right now.", 503, code="TTS_UNAVAILABLE")

    audio_path = os.path.join(voice.AUDIO_DIR, f"{filename_no_ext}.wav")
    try:
        with open(audio_path, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass
    return Response(data, mimetype="audio/wav")


# --------------- Telephony (Twilio) ---------------

@app.get("/api/audio/<int:call_id>.wav")
def api_call_audio(call_id: int):
    """Public by necessity - Twilio's media servers fetch this URL directly
    while placing the call and can't send a session cookie. Only serves
    audio for a call that actually exists and actually generated one."""
    from flask import Response

    with db.get_conn() as conn:
        row = conn.execute("SELECT audio_filename FROM calls WHERE id = %s", (call_id,)).fetchone()
    if not row or not row["audio_filename"]:
        return api_error("Not found", 404, code="NOT_FOUND")

    audio_path = os.path.join(voice.AUDIO_DIR, f"{row['audio_filename']}.wav")
    if not os.path.isfile(audio_path):
        return api_error("Not found", 404, code="NOT_FOUND")
    with open(audio_path, "rb") as f:
        data = f.read()
    return Response(data, mimetype="audio/wav")


@app.post("/api/webhooks/twilio/status")
def api_twilio_status_webhook():
    """Twilio's asynchronous call-status callback. Verified via Twilio's
    request signature (X-Twilio-Signature) since this endpoint has no
    session auth - anyone can find the URL, so the signature is what
    proves a request actually came from Twilio before we trust it enough
    to write to a call record."""
    from twilio.request_validator import RequestValidator

    call_sid = request.form.get("CallSid")
    account_sid = request.form.get("AccountSid")
    call_status = request.form.get("CallStatus")
    if not call_sid or not call_status:
        return api_error("Missing required fields", 400, code="MISSING_FIELDS")

    live_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    test_sid = os.environ.get("TWILIO_TEST_ACCOUNT_SID")
    if account_sid == live_sid:
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    elif account_sid == test_sid:
        auth_token = os.environ.get("TWILIO_TEST_AUTH_TOKEN", "")
    else:
        return api_error("Unrecognized account", 403, code="FORBIDDEN")

    # Twilio signs the PUBLIC URL it was given (e.g. the ngrok tunnel), but
    # Flask's request.url reflects whatever it actually received the request
    # on (localhost, behind the tunnel) - validating against the wrong one
    # makes every real webhook fail signature checking. Reconstruct the
    # public URL from PUBLIC_BASE_URL when it's configured.
    public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    request_url = f"{public_base}{request.full_path}".rstrip("?") if public_base else request.url

    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(auth_token)
    if not validator.validate(request_url, request.form.to_dict(), signature):
        return api_error("Invalid signature", 403, code="FORBIDDEN")

    call = db.get_call_by_provider_sid(call_sid)
    if not call:
        # Not one of ours (or arrived before we saved the SID) - ack anyway
        # so Twilio doesn't retry indefinitely.
        return api_ok({"received": True})

    call_status_internal, outcome = twilio_client.map_status(call_status)
    if call_status in twilio_client.TERMINAL_STATUSES:
        db.update_call(
            call["id"],
            status=call_status_internal,
            outcome=outcome,
            duration_sec=int(request.form.get("CallDuration") or 0),
            ended_at=db.now_iso(),
        )
    db.append_call_event(
        call["id"],
        {"ts": db.now_iso(), "type": "webhook", "message": f"Twilio status: {call_status}"},
    )
    return api_ok({"received": True})


@app.get("/api/settings")
@login_required_api
def api_get_settings():
    return api_ok({"settings": db.get_settings(session["organization_id"])})


@app.put("/api/settings")
@require_permission("manage_settings")
def api_put_settings():
    payload = request.get_json(silent=True) or {}
    allowed = {
        "voice_id", "voice_speed", "agent_name", "opening_message",
        "calling_mode", "max_calls", "delay_ms", "concurrency",
        "retry_max_attempts", "retry_delay_no_answer_ms", "retry_delay_busy_ms",
        "calling_hours_enabled", "calling_hours_start", "calling_hours_end",
        "calling_days", "timezone", "twilio_mode",
    }
    data = {k: v for k, v in payload.items() if k in allowed}
    if "twilio_mode" in data and data["twilio_mode"] not in ("test", "live"):
        return api_error("twilio_mode must be 'test' or 'live'", 400, code="INVALID_VALUE")
    db.save_settings(session["organization_id"], data)
    db.add_audit_log("settings_update", actor_id=session["user_id"], actor_username=session.get("username"),
                      organization_id=session["organization_id"], entity="settings", metadata=data,
                      ip_address=client_ip())
    return api_ok({"settings": db.get_settings(session["organization_id"])})


@app.get("/api/notifications")
@login_required_api
def api_notifications():
    items = db.get_notifications(session["user_id"])
    return api_ok({"notifications": items})


@app.post("/api/notifications/read")
@login_required_api
def api_notifications_read():
    db.mark_notifications_read(session["user_id"])
    return api_ok({"message": "ok"})


@app.get("/api/health")
def api_health():
    db_status = "healthy"
    try:
        with db.get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "critical"

    telephony = check_telephony()
    tts = voice.tts_available()
    components = {
        "database": db_status,
        "telephony": "healthy" if telephony.get("available") else ("warning" if telephony.get("configured") else "critical"),
        "voice_engine": "healthy" if tts.get("available") else "critical",
    }
    overall = "critical" if "critical" in components.values() else ("warning" if "warning" in components.values() else "healthy")

    return api_ok({
        "status": overall,
        "components": components,
        "telephony": telephony,
        "tts": tts,
    })


# --------------- Admin: users, login history, audit logs ---------------

@app.get("/api/admin/users")
@require_permission("manage_users")
def api_admin_list_users():
    return api_ok({"users": db.list_users(session["organization_id"])})


@app.post("/api/admin/users")
@require_permission("manage_users")
def api_admin_create_user():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    role = payload.get("role") or "AGENT"
    if not username or not password:
        return api_error("Username and password are required", 400, code="MISSING_FIELDS")
    if role not in ("SUPER_ADMIN", "ADMIN", "MANAGER", "AGENT", "VIEWER"):
        return api_error("Invalid role", 400, code="INVALID_ROLE")
    if db.get_user_by_username(username, organization_id=session["organization_id"]):
        return api_error("That username is already taken", 409, code="USERNAME_TAKEN")

    user_id = db.create_user(
        username, password,
        client_name=session.get("client_name") or "Outreach",
        organization_id=session["organization_id"],
        role=role,
        email=payload.get("email"),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
    )
    db.add_audit_log("user_create", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="user", entity_id=user_id, metadata={"username": username, "role": role}, ip_address=client_ip())
    return api_ok({"user": db.update_user(user_id)})


@app.put("/api/admin/users/<int:user_id>")
@require_permission("manage_users")
def api_admin_update_user(user_id: int):
    payload = request.get_json(silent=True) or {}
    role = payload.get("role")
    if role and role not in ("SUPER_ADMIN", "ADMIN", "MANAGER", "AGENT", "VIEWER"):
        return api_error("Invalid role", 400, code="INVALID_ROLE")
    status = payload.get("status")
    if status and status not in ("active", "inactive"):
        return api_error("Invalid status", 400, code="INVALID_STATUS")
    if user_id == session["user_id"] and (role or status == "inactive"):
        return api_error("You cannot change your own role or deactivate your own account.", 400, code="SELF_MODIFY")

    user = db.update_user(
        user_id, role=role, status=status,
        email=payload.get("email"), first_name=payload.get("first_name"), last_name=payload.get("last_name"),
    )
    db.add_audit_log("user_update", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="user", entity_id=user_id, metadata=payload, ip_address=client_ip())
    return api_ok({"user": user})


@app.post("/api/admin/users/<int:user_id>/reset-password")
@require_permission("manage_users")
def api_admin_reset_password(user_id: int):
    payload = request.get_json(silent=True) or {}
    new_password = payload.get("password") or ""
    if len(new_password) < 8:
        return api_error("Password must be at least 8 characters", 400, code="WEAK_PASSWORD")
    db.set_user_password(user_id, new_password)
    db.add_audit_log("user_password_reset", actor_id=session["user_id"], actor_username=session.get("username"),
                                            organization_id=session["organization_id"], entity="user", entity_id=user_id, ip_address=client_ip())
    return api_ok({"reset": True})


@app.get("/api/admin/login-history")
@require_permission("view_audit_logs")
def api_admin_login_history():
    result = db.get_login_history(
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 25)),
        user_id=int(request.args["user_id"]) if request.args.get("user_id") else None,
        organization_id=session["organization_id"],
    )
    return api_ok(result)


@app.get("/api/admin/audit-logs")
@require_permission("view_audit_logs")
def api_admin_audit_logs():
    result = db.get_audit_logs(
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 25)),
        action=request.args.get("action", ""),
        entity=request.args.get("entity", ""),
        organization_id=session["organization_id"],
    )
    return api_ok(result)


# --------------- SPA ---------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    # Prefer built frontend; fall back to simple message
    if path.startswith("api/"):
        return api_error("Not found", 404)
    if os.path.isdir(FRONTEND_DIST):
        target = os.path.join(FRONTEND_DIST, path)
        if path and os.path.isfile(target):
            return send_from_directory(FRONTEND_DIST, path)
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.isfile(index):
            return send_from_directory(FRONTEND_DIST, "index.html")
    return (
        "<h1>Outreach</h1>"
        "<p>The application interface is not available yet. Please contact your administrator.</p>",
        200,
        {"Content-Type": "text/html"},
    )


@app.errorhandler(Exception)
def handle_unexpected(exc):
    from werkzeug.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return exc
    if app.debug:
        return api_error(str(exc), 500, trace=traceback.format_exc())
    return api_error("Internal server error", 500)


if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
