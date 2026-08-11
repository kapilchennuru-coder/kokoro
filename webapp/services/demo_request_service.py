"""Public marketing-site 'Request a Demo' lead capture. Deliberately does
not touch organization/contact/campaign data - the public website must
never reach patient-facing tables."""

from __future__ import annotations

import re

import db

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

RATE_LIMIT_WINDOW_MIN = 60
RATE_LIMIT_MAX = 5

REQUIRED_FIELDS = (
    "first_name", "last_name", "email", "company_name", "country", "phone", "industry",
    "company_size", "monthly_call_volume", "preferred_demo_date", "preferred_demo_time", "timezone",
)

REQUIRED_ADDRESS_FIELDS = ("line1", "line2", "city", "state", "postal_code", "country")

ADDRESS_FIELD_LABELS = {
    "line1": "Address Line 1", "line2": "Address Line 2", "city": "City",
    "state": "State / Province", "postal_code": "Postal / ZIP Code", "country": "Address Country",
}


def _validate_phone(dial_and_number: str) -> str | None:
    """dial_and_number looks like '+91 9391944195' - matches what the
    frontend sends (dial code + number joined with a space)."""
    digits = re.sub(r"\D", "", dial_and_number)
    if dial_and_number.strip().startswith("+91"):
        # digits includes the leading 91 from the dial code, so the actual
        # subscriber number is everything after that.
        national_number = digits[2:] if digits.startswith("91") else digits
        if len(national_number) != 10:
            return "Please enter a valid 10-digit mobile number."
        return None
    if len(digits) < 6:
        return "Enter a valid phone number."
    return None


def submit(payload: dict, ip_address: str) -> dict:
    for field in REQUIRED_FIELDS:
        if not str(payload.get(field) or "").strip():
            raise ValueError(f"{field.replace('_', ' ').title()} is required.")

    email = str(payload.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")

    phone = str(payload.get("phone") or "").strip()
    phone_error = _validate_phone(phone)
    if phone_error:
        raise ValueError(phone_error)

    # "Other" industry: the free-text field is required and becomes the
    # actual stored industry, so downstream (admin dashboard, exports) sees
    # a real industry name instead of the literal word "Other".
    industry = str(payload.get("industry") or "").strip()
    if industry == "Other":
        other_industry = str(payload.get("other_industry") or "").strip()
        if not other_industry:
            raise ValueError("Please specify your industry.")
        industry = other_industry

    address = payload.get("address") or {}
    for field in REQUIRED_ADDRESS_FIELDS:
        if not str(address.get(field) or "").strip():
            raise ValueError(f"{ADDRESS_FIELD_LABELS[field]} is required.")

    if not payload.get("consent"):
        raise ValueError("Please agree to be contacted to submit this request.")

    if db.count_recent_demo_requests(ip_address, RATE_LIMIT_WINDOW_MIN) >= RATE_LIMIT_MAX:
        raise ValueError("Too many requests. Please try again later.")

    clean = {
        "first_name": str(payload.get("first_name") or "").strip()[:150],
        "last_name": str(payload.get("last_name") or "").strip()[:150],
        "email": email[:255],
        "company_name": str(payload.get("company_name") or "").strip()[:255],
        "job_title": str(payload.get("job_title") or "").strip()[:150],
        "country": str(payload.get("country") or "").strip()[:100],
        "phone": phone[:40],
        "website": str(payload.get("website") or "").strip()[:255],
        "industry": industry[:150],
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
