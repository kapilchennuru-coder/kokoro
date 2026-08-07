# =============================================================
# AI Calling Dashboard — Flask JSON API
#
# Reuses Kokoro voice generation (voice.py) and Asterisk AMI
# (ami_client.py). React SPA is served from frontend/dist.
# =============================================================

from __future__ import annotations

import os
import traceback

from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import db
import voice
from services import campaign_service, contact_service
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


def api_error(message: str, status: int = 400, **extra):
    body = {"ok": False, "error": message, **extra}
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

@app.post("/api/auth/login")
def api_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = db.get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return api_error("Invalid username or password", 401)
    session["user_id"] = user["id"]
    session["client_name"] = user["client_name"]
    session["username"] = user["username"]
    return api_ok({
        "user": {
            "id": user["id"],
            "username": user["username"],
            "client_name": user["client_name"],
        }
    })


@app.post("/api/auth/logout")
def api_logout():
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
        }
    })


# --------------- Dashboard ---------------

@app.get("/api/dashboard")
@login_required_api
def api_dashboard():
    uid = session["user_id"]
    contacts = db.count_contacts(uid)
    active = db.get_active_campaign(uid)
    recent_calls = db.get_calls(uid, page=1, page_size=8)
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
        "notifications": db.get_notifications(uid, 10),
    })


# --------------- Contacts / Excel ---------------

@app.get("/api/contacts")
@login_required_api
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
@login_required_api
def api_contact_detail(contact_id: int):
    contact = contact_service.get_contact(session["user_id"], contact_id)
    if not contact:
        return api_error("Patient not found", 404)
    return api_ok({"contact": contact, "patient": contact})


@app.put("/api/contacts/<int:contact_id>")
@login_required_api
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
        return api_error("Patient not found", 404)
    return api_ok({"contact": contact, "patient": contact})


@app.delete("/api/contacts/<int:contact_id>")
@login_required_api
def api_delete_contact(contact_id: int):
    ok = contact_service.delete_contact(session["user_id"], contact_id)
    if not ok:
        return api_error("Patient not found", 404)
    return api_ok({"deleted": True})


@app.get("/api/contact-lists")
@login_required_api
def api_contact_lists():
    return api_ok({"lists": contact_service.list_lists(session["user_id"])})


@app.post("/api/contacts/upload")
@login_required_api
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
@login_required_api
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
@login_required_api
def api_discard_pending():
    contact_service.cancel_pending(session["user_id"])
    return api_ok({"cancelled": True, "persisted": False})


@app.post("/api/contacts/upload/preview")
@login_required_api
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
@login_required_api
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
    return api_ok(result)


@app.post("/api/contacts/upload/cancel")
@login_required_api
def api_cancel_import():
    contact_service.cancel_pending(session["user_id"])
    return api_ok({"cancelled": True, "persisted": False})


# --------------- Campaigns ---------------

@app.get("/api/campaigns")
@login_required_api
def api_campaigns():
    return api_ok({"campaigns": campaign_service.list_campaigns(session["user_id"])})


@app.post("/api/campaigns")
@login_required_api
def api_create_campaign():
    payload = request.get_json(silent=True) or {}
    try:
        campaign = campaign_service.create_campaign(session["user_id"], payload)
    except ValueError as exc:
        return api_error(str(exc))
    except Exception as exc:
        return api_error(f"Could not create campaign: {exc}")
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
        "telephony": check_telephony(),
        "tts": voice.tts_available(),
    })


@app.post("/api/calling/start")
@login_required_api
def api_start_calling():
    try:
        campaign = campaign_service.start_calling_ready_patients(session["user_id"])
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/start")
@login_required_api
def api_start_campaign(campaign_id: int):
    try:
        campaign = campaign_service.start_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/pause")
@login_required_api
def api_pause_campaign(campaign_id: int):
    try:
        campaign = campaign_service.pause_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/resume")
@login_required_api
def api_resume_campaign(campaign_id: int):
    try:
        campaign = campaign_service.resume_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok({"campaign": campaign})


@app.post("/api/campaigns/<int:campaign_id>/stop")
@login_required_api
def api_stop_campaign(campaign_id: int):
    try:
        campaign = campaign_service.stop_campaign(session["user_id"], campaign_id)
    except ValueError as exc:
        return api_error(str(exc))
    return api_ok({"campaign": campaign})


# --------------- Calls ---------------

@app.get("/api/calls")
@login_required_api
def api_calls():
    result = db.get_calls(
        session["user_id"],
        search=request.args.get("search", ""),
        status=request.args.get("status", ""),
        campaign_id=int(request.args["campaign_id"]) if request.args.get("campaign_id") else None,
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 25)),
    )
    return api_ok(result)


@app.get("/api/calls/<int:call_id>")
@login_required_api
def api_call_detail(call_id: int):
    call = db.get_call(session["user_id"], call_id)
    if not call:
        return api_error("Call not found", 404)
    return api_ok({"call": call})


# --------------- Settings / voices / health ---------------

@app.get("/api/voices")
@login_required_api
def api_voices():
    return api_ok({"voices": list_voices(), "agents": list_agents()})


@app.get("/api/settings")
@login_required_api
def api_get_settings():
    return api_ok({"settings": db.get_settings(session["user_id"])})


@app.put("/api/settings")
@login_required_api
def api_put_settings():
    payload = request.get_json(silent=True) or {}
    allowed = {
        "voice_id", "voice_speed", "agent_name", "opening_message",
        "calling_mode", "max_calls", "delay_ms", "concurrency",
    }
    data = {k: v for k, v in payload.items() if k in allowed}
    db.save_settings(session["user_id"], data)
    return api_ok({"settings": db.get_settings(session["user_id"])})


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
    return api_ok({
        "telephony": check_telephony(),
        "tts": voice.tts_available(),
    })


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
