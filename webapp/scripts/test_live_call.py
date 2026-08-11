"""One-off manual test: places a single REAL Twilio call using live
credentials, playing Patient 1's actual real Kokoro-generated reminder
message via <Play> (requires PUBLIC_BASE_URL - an ngrok tunnel or similar -
so Twilio can fetch the audio; falls back to Twilio's <Say> otherwise).

Reuses the exact same twilio_client/voice/db code the real campaign runner
uses - not a separate reimplementation. Creates a real `calls` row so it
also shows up in Calls history like any other call.

Usage (from webapp/):
    python scripts/test_live_call.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import db  # noqa: E402
import voice  # noqa: E402
from services import twilio_client  # noqa: E402
from services.call_runner import _render_script  # noqa: E402

# Set via env vars, not hardcoded - this script places a REAL call, and a
# hardcoded personal number/name here would otherwise end up committed to
# git history. OVERRIDE_NAME is optional; leave unset to use the real
# patient's name instead.
TO_NUMBER = os.environ.get("TEST_CALL_TO_NUMBER", "")
OVERRIDE_NAME = os.environ.get("TEST_CALL_OVERRIDE_NAME") or None

ZEBL_OPENING = (
    "Hello {name}, this is Zebl India AR calling. "
    "Our records show you have a pending balance of {balance_display}. "
    "Please contact the billing office at your earliest convenience. "
    "Thanks for taking the call."
)


def main() -> None:
    if not TO_NUMBER:
        print("Set TEST_CALL_TO_NUMBER (E.164, e.g. +15551234567) before running this - "
              "no default number is hardcoded here on purpose. Aborting.")
        return

    if not twilio_client.is_configured("live"):
        print("Live Twilio credentials are not fully set in .env "
              "(TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER). Aborting.")
        return

    print("Checking Twilio account...")
    account = twilio_client.check_account("live")
    print(f"  {account}")
    if not account.get("available"):
        print("Account check failed - aborting before placing a real call.")
        return

    from_number = twilio_client.from_number()
    print(f"\nChecking Voice capability on {from_number}...")
    try:
        client = twilio_client.get_client("live")
        numbers = client.incoming_phone_numbers.list(phone_number=from_number)
        if numbers:
            caps = numbers[0].capabilities
            print(f"  capabilities: {caps}")
            if not caps.get("voice"):
                print("  WARNING: this number does not have Voice capability enabled "
                      "in the Twilio Console (Phone Numbers -> this number -> Voice). "
                      "The call will likely fail.")
        else:
            print(f"  WARNING: {from_number} was not found on this account - double-check TWILIO_FROM_NUMBER.")
    except Exception as exc:
        print(f"  Could not check number capabilities ({exc}) - continuing anyway.")

    user = db.get_user_by_username("demo")
    if not user:
        print("No 'demo' user found - aborting.")
        return
    organization_id = user["organization_id"]

    contacts = db.get_contacts(organization_id, page=1, page_size=1, sort_by="id", sort_dir="asc")["items"]
    if not contacts:
        print("No patients found - import patients.xlsx first.")
        return
    patient = contacts[0]
    if OVERRIDE_NAME:
        patient = {**patient, "name": OVERRIDE_NAME}
    print(f"\nPatient 1: {patient['name']} - {patient.get('balance_display')} - {patient.get('hospital')}")

    script = _render_script(ZEBL_OPENING, patient)
    print(f"\nText to be converted to speech:\n  \"{script}\"\n")

    print("\nGenerating Kokoro audio for the real message...")
    audio_name = voice.generate_call_audio(
        contact_id=str(patient["id"]), script=script, voice_name="af_jessica", speed=1.0,
    )
    print(f"  Generated {audio_name}.wav in {voice.AUDIO_DIR}")

    # Real `calls` row, exactly like a campaign call, so /api/audio/<id>.wav
    # can serve it and it shows up in Calls history.
    call_id = db.create_call(organization_id, campaign_id=None, contact_id=patient["id"], script_text=script, patient=patient)
    db.update_call(call_id, audio_filename=audio_name)

    public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not public_base:
        print("\nWARNING: PUBLIC_BASE_URL is not set - Twilio can't fetch the audio file, "
              "the call will use <Say> instead of the real Kokoro audio.")
        audio_url = None
    else:
        audio_url = f"{public_base}/api/audio/{call_id}.wav"
        print(f"\nAudio will be played from: {audio_url}")

    print(f"\nPlacing LIVE call to {TO_NUMBER} from {from_number}...")
    result = twilio_client.place_call(to=TO_NUMBER, script_text=script, audio_url=audio_url, mode="live")
    print(f"  {result}")

    if result.get("status") == "error" or not result.get("sid"):
        print("\nCall was not placed - see the error above.")
        return

    call_sid = result["sid"]
    db.update_call(call_id, provider_call_sid=call_sid)
    print(f"\nCall SID: {call_sid}")
    print("Polling for status (up to ~65s)...")

    seen = set()
    final_status = "error"
    final_duration = 0
    deadline = time.time() + twilio_client.MAX_POLL_SEC
    while time.time() < deadline:
        status = twilio_client.fetch_status(call_sid, "live")
        if status.get("status") not in seen:
            seen.add(status.get("status"))
            print(f"  status: {status}")
        if status.get("status") in twilio_client.TERMINAL_STATUSES:
            final_status = status.get("status")
            final_duration = int(status.get("duration") or 0)
            break
        time.sleep(twilio_client.POLL_INTERVAL_SEC)

    call_status, outcome = twilio_client.map_status(final_status)
    db.update_call(call_id, status=call_status, outcome=outcome, duration_sec=final_duration, ended_at=db.now_iso())

    print(f"\nFinal outcome: {outcome}")
    print("Done. Also visible in the app under Calls history.")


if __name__ == "__main__":
    main()
