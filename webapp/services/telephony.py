"""Telephony health checks for Twilio Voice - never pretend calls succeed."""

from __future__ import annotations

import os

import db
from services import twilio_client


def resolve_mode(organization_id: int | None = None) -> str:
    """The Twilio SID/token pair is global (env vars), but which pair is
    active (test vs live) is a per-organization Settings choice. Public/
    unauthenticated callers (like /api/health) have no organization_id, so
    they fall back to the env-var default."""
    if organization_id is not None:
        return db.get_settings(organization_id).get("twilio_mode", "test")
    return os.environ.get("TWILIO_MODE", "test")


def check_telephony(organization_id: int | None = None) -> dict:
    mode = resolve_mode(organization_id)
    result = twilio_client.check_account(mode)
    result["mode"] = mode
    result["from_number"] = twilio_client.from_number() or None
    return result
