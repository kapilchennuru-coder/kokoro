"""Public marketing-site 'Request a Demo' lead capture. Deliberately does
not touch organization/contact/campaign data - the public website must
never reach patient-facing tables."""

from __future__ import annotations

import re

import db

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"[\d]{6,}")

RATE_LIMIT_WINDOW_MIN = 60
RATE_LIMIT_MAX = 5

REQUIRED_FIELDS = ("first_name", "last_name", "email", "company_name", "country", "phone", "industry")


def submit(payload: dict, ip_address: str) -> dict:
    # Honeypot: a real visitor never fills this hidden field in; a bot
    # filling every input on the page will. Fail silently-ish (still a
    # ValueError, but a generic one) rather than confirming to the bot
    # which specific check tripped.
    if (payload.get("website_hp") or "").strip():
        raise ValueError("Unable to submit your request. Please try again.")

    for field in REQUIRED_FIELDS:
        if not str(payload.get(field) or "").strip():
            raise ValueError(f"{field.replace('_', ' ').title()} is required.")

    email = str(payload.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")

    phone = str(payload.get("phone") or "").strip()
    if not PHONE_RE.search(phone):
        raise ValueError("Enter a valid phone number.")

    if not payload.get("consent"):
        raise ValueError("Please agree to be contacted to submit this request.")

    if db.count_recent_demo_requests(ip_address, RATE_LIMIT_WINDOW_MIN) >= RATE_LIMIT_MAX:
        raise ValueError("Too many requests. Please try again later.")

    address = payload.get("address") or {}
    clean = {
        "first_name": str(payload.get("first_name") or "").strip()[:150],
        "last_name": str(payload.get("last_name") or "").strip()[:150],
        "email": email[:255],
        "company_name": str(payload.get("company_name") or "").strip()[:255],
        "job_title": str(payload.get("job_title") or "").strip()[:150],
        "country": str(payload.get("country") or "").strip()[:100],
        "phone": phone[:40],
        "website": str(payload.get("website") or "").strip()[:255],
        "industry": str(payload.get("industry") or "").strip()[:150],
        "company_size": str(payload.get("company_size") or "").strip()[:50],
        "address": {
            "line1": str(address.get("line1") or "").strip()[:255],
            "line2": str(address.get("line2") or "").strip()[:255],
            "city": str(address.get("city") or "").strip()[:150],
            "state": str(address.get("state") or "").strip()[:150],
            "postal_code": str(address.get("postal_code") or "").strip()[:30],
        },
        "automation_need": str(payload.get("automation_need") or "").strip(),
        "monthly_call_volume": str(payload.get("monthly_call_volume") or "").strip()[:50],
        "current_process": str(payload.get("current_process") or "").strip(),
        "preferred_demo_date": str(payload.get("preferred_demo_date") or "").strip()[:20],
        "preferred_demo_time": str(payload.get("preferred_demo_time") or "").strip()[:20],
        "timezone": str(payload.get("timezone") or "").strip()[:100],
        "message": str(payload.get("message") or "").strip(),
        "consent": True,
    }

    request_id = db.create_demo_request(clean, ip_address=ip_address)
    return {"id": request_id}


def list_requests(page: int = 1, page_size: int = 25, status: str = "") -> dict:
    return db.get_demo_requests(page=page, page_size=page_size, status=status)


def update_status(request_id: int, status: str | None, notes: str | None):
    valid_statuses = {"NEW", "CONTACTED", "QUALIFIED", "DEMO_SCHEDULED", "CLOSED"}
    if status is not None and status not in valid_statuses:
        raise ValueError("Invalid status.")
    return db.update_demo_request(request_id, status=status, notes=notes)
