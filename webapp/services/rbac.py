"""Role-based access control. Server-side only - a role/permission is never
trusted if it comes from the request; it is always read from the session,
which is set once at login from the database."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request, session

ROLES = ("SUPER_ADMIN", "ADMIN", "MANAGER", "AGENT", "VIEWER")

PERMISSIONS: dict[str, set[str]] = {
    "SUPER_ADMIN": {
        "view_patients", "edit_patients", "delete_patients", "import_patients",
        "create_campaign", "start_campaign", "pause_campaign", "stop_campaign",
        "view_calls", "view_reports", "manage_users", "manage_voices",
        "manage_settings", "view_audit_logs", "manage_integrations", "manage_leads",
    },
    "ADMIN": {
        "view_patients", "edit_patients", "delete_patients", "import_patients",
        "create_campaign", "start_campaign", "pause_campaign", "stop_campaign",
        "view_calls", "view_reports", "manage_users", "manage_voices",
        "manage_settings", "view_audit_logs", "manage_integrations", "manage_leads",
    },
    "MANAGER": {
        "view_patients", "edit_patients", "delete_patients", "import_patients",
        "create_campaign", "start_campaign", "pause_campaign", "stop_campaign",
        "view_calls", "view_reports", "manage_voices", "manage_settings",
    },
    "AGENT": {
        "view_patients", "edit_patients", "import_patients",
        "start_campaign", "pause_campaign", "stop_campaign",
        "view_calls",
    },
    "VIEWER": {
        "view_patients", "view_calls", "view_reports",
    },
}

ADMIN_ROLES = {"SUPER_ADMIN", "ADMIN"}


def has_permission(role: str | None, permission: str) -> bool:
    return permission in PERMISSIONS.get(role or "", set())


def current_role() -> str | None:
    return session.get("role")


def _forbidden(message: str):
    return jsonify({"ok": False, "error": message}), 403


def require_permission(permission: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            if not has_permission(session.get("role"), permission):
                return _forbidden("You do not have permission to do that.")
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_role(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            if session.get("role") not in roles:
                return _forbidden("You do not have permission to do that.")
            return view(*args, **kwargs)

        return wrapped

    return decorator


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""
