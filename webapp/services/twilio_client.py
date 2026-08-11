"""Twilio Voice adapter - places real outbound calls and reports real
outcomes. Test-credential calls are clearly labeled "simulated" everywhere
(never folded into real answered/no-answer/busy counters) so nobody can
mistake a safe dry run for an actual placed call.
"""

from __future__ import annotations

import os

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

TERMINAL_STATUSES = {"completed", "busy", "no-answer", "failed", "canceled"}
POLL_INTERVAL_SEC = 2
MAX_POLL_SEC = 65   # a little past Twilio's own default ~60s ring timeout
CALL_TIMEOUT_SEC = 30  # how long Twilio itself lets the destination ring

_clients: dict[str, Client] = {}


def _credentials(mode: str) -> tuple[str, str]:
    if mode == "live":
        return os.environ.get("TWILIO_ACCOUNT_SID", ""), os.environ.get("TWILIO_AUTH_TOKEN", "")
    return os.environ.get("TWILIO_TEST_ACCOUNT_SID", ""), os.environ.get("TWILIO_TEST_AUTH_TOKEN", "")


def is_configured(mode: str) -> bool:
    sid, token = _credentials(mode)
    return bool(sid and token and os.environ.get("TWILIO_FROM_NUMBER"))


def from_number() -> str:
    return os.environ.get("TWILIO_FROM_NUMBER", "")


def get_client(mode: str) -> Client | None:
    sid, token = _credentials(mode)
    if not sid or not token:
        return None
    cached = _clients.get(mode)
    if cached is not None:
        return cached
    client = Client(sid, token)
    _clients[mode] = client
    return client


def check_account(mode: str) -> dict:
    """Real check - actually asks Twilio to confirm these credentials work,
    the same way check_telephony() used to really probe the AMI socket."""
    if not is_configured(mode):
        return {"available": False, "configured": False, "detail": f"Twilio {mode} credentials are not set."}

    client = get_client(mode)
    sid, _ = _credentials(mode)
    try:
        account = client.api.accounts(sid).fetch()
        return {
            "available": account.status == "active",
            "configured": True,
            "detail": "Ready" if account.status == "active" else f"Twilio account status: {account.status}",
            "mode": mode,
        }
    except TwilioRestException as exc:
        return {"available": False, "configured": True, "detail": "Twilio credentials were rejected.", "error": str(exc)}
    except Exception:
        return {"available": False, "configured": True, "detail": "Unable to reach Twilio right now."}


def build_twiml(script_text: str, audio_url: str | None = None) -> str:
    """<Play> the real Kokoro audio when it's reachable at a public URL;
    otherwise fall back to Twilio's own <Say> so the call still carries the
    message even without a public audio URL configured yet.

    Leads with a short <Pause> - on some PSTN/landline routes Twilio marks
    the call "answered" a beat before the two-way audio path is actually
    cut through, so playback started immediately gets clipped at the start
    and only the tail is audible. The pause gives the media path time to
    settle before anything is played. Kept short (1s) since Twilio's own
    round-trip to fetch the <Play> URL adds another beat of silence on top
    of whatever we set here - the two stack into what the callee hears.
    """
    response = VoiceResponse()
    response.pause(length=1)
    if audio_url:
        response.play(audio_url)
    else:
        response.say(script_text, voice="Polly.Joanna")
    return str(response)


def place_call(to: str, script_text: str, audio_url: str | None, mode: str,
               status_callback_url: str | None = None) -> dict:
    if not is_configured(mode):
        return {"status": "error", "detail": f"Twilio {mode} credentials are not configured.", "sid": None, "simulated": False}

    client = get_client(mode)
    twiml = build_twiml(script_text, audio_url)
    kwargs = {
        "to": to,
        "from_": from_number(),
        "twiml": twiml,
        "timeout": CALL_TIMEOUT_SEC,
    }
    if status_callback_url:
        kwargs["status_callback"] = status_callback_url
        kwargs["status_callback_event"] = ["initiated", "ringing", "answered", "completed"]
        kwargs["status_callback_method"] = "POST"

    try:
        call = client.calls.create(**kwargs)
    except TwilioRestException as exc:
        return {"status": "error", "detail": "Unable to place this call right now.", "sid": None, "simulated": False, "raw": str(exc)}
    except Exception:
        return {"status": "error", "detail": "Unable to process this request right now.", "sid": None, "simulated": False}

    return {"status": call.status, "sid": call.sid, "simulated": mode == "test"}


def map_status(status: str, simulated: bool = False) -> tuple[str, str]:
    """Return our internal (call_status, outcome) from a Twilio call status.
    A simulated (test-credential) call never gets a real outcome from
    Twilio, so it's tagged distinctly rather than guessed at as answered/
    failed/etc. Shared by the campaign runner and the status webhook so
    there is exactly one place this mapping is defined."""
    if simulated:
        return ("completed", "simulated")
    mapping = {
        "completed": ("completed", "answered"),
        "busy": ("failed", "busy"),
        "no-answer": ("no_answer", "no_answer"),
        "failed": ("failed", "failed"),
        "canceled": ("failed", "failed"),
        "error": ("failed", "failed"),
        "telephony_unavailable": ("failed", "failed"),
        "timeout": ("failed", "failed"),
    }
    return mapping.get(status, ("failed", "failed"))


def fetch_status(call_sid: str, mode: str) -> dict:
    client = get_client(mode)
    if not client:
        return {"status": "error", "detail": "Twilio is not configured."}
    try:
        call = client.calls(call_sid).fetch()
        return {"status": call.status, "duration": call.duration, "detail": call.status}
    except TwilioRestException:
        return {"status": "error", "detail": "Unable to check call status right now."}
