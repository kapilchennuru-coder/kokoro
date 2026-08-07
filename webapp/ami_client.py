# =============================================================
# Thin AMI client shared by the web app to originate calls and read
# back whether the call was actually answered or not.
#
# Reuses the same AMI login/Originate approach as
# ../asterisk/make_call.py, but parses the synchronous Originate
# response to get a real answered/no-answer/busy/failed status
# instead of just firing the call and hoping.
#
# Asterisk's Originate action (without Async: true) blocks until the
# call is answered or times out, and returns a "Reason" code in its
# response:
#   1 = Unallocated / hangup before answer
#   2 = No user response (no answer)
#   3 = No answer (rang out)
#   4 = Answered
#   5 = Call rejected / congestion
#   8 = No answer
# Anything not "4" is treated as "not answered" for our purposes.
# =============================================================

import os
import socket
import time

from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASTERISK_ENV_PATH = os.path.join(BASE_DIR, "..", "asterisk", ".env")

_env = dotenv_values(ASTERISK_ENV_PATH)

AMI_HOST = os.environ.get("AMI_HOST", "localhost")
AMI_PORT = int(os.environ.get("AMI_PORT", "5038"))
AMI_USER = _env.get("AMI_USERNAME", "")
AMI_SECRET = _env.get("AMI_SECRET", "")

REASON_ANSWERED = "4"

REASON_TEXT = {
    "1": "failed",
    "2": "no_answer",
    "3": "no_answer",
    "4": "answered",
    "5": "rejected",
    "8": "no_answer",
}


def _recv_all(sock, timeout=35):
    sock.settimeout(timeout)
    chunks = []
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\r\n\r\n" in chunk and len(chunks) > 1:
                break
    except socket.timeout:
        pass
    return b"".join(chunks).decode("utf-8", errors="ignore")


def _parse_field(text, field_name):
    for line in text.splitlines():
        if line.lower().startswith(field_name.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None


def place_call(destination_number: str, audio_filename_no_extension: str) -> dict:
    """
    Originates a call via Asterisk/VoIP Office and blocks until the
    call is answered or times out. Returns a dict describing what
    actually happened, for storing against the patient's call record.
    """
    if not AMI_USER or not AMI_SECRET:
        return {"status": "error", "detail": "AMI credentials not configured"}

    try:
        sock = socket.create_connection((AMI_HOST, AMI_PORT), timeout=10)
    except OSError as exc:
        return {"status": "error", "detail": f"could not reach Asterisk AMI: {exc}"}

    try:
        sock.recv(1024)  # banner

        login_msg = (
            "Action: Login\r\n"
            f"Username: {AMI_USER}\r\n"
            f"Secret: {AMI_SECRET}\r\n\r\n"
        )
        sock.sendall(login_msg.encode("utf-8"))
        time.sleep(0.3)
        login_resp = _recv_all(sock, timeout=5)
        if "Success" not in login_resp:
            return {"status": "error", "detail": "AMI login failed", "raw": login_resp}

        action_id = f"call-{int(time.time() * 1000)}"
        originate_msg = (
            "Action: Originate\r\n"
            f"ActionID: {action_id}\r\n"
            f"Channel: PJSIP/{destination_number}@voipoffice-endpoint\r\n"
            "Context: outbound-calls\r\n"
            "Exten: play-reminder\r\n"
            "Priority: 1\r\n"
            f"Variable: AUDIO_FILE={audio_filename_no_extension}\r\n"
            "CallerID: Zebl AR <1000>\r\n"
            "Timeout: 30000\r\n\r\n"
        )
        sock.sendall(originate_msg.encode("utf-8"))
        raw = _recv_all(sock, timeout=35)

        reason = _parse_field(raw, "Reason")
        response = _parse_field(raw, "Response")

        if response and response.lower() == "error":
            return {"status": "error", "detail": _parse_field(raw, "Message") or "originate failed", "raw": raw}

        status = REASON_TEXT.get(reason, "unknown")
        return {"status": status, "reason_code": reason, "raw": raw}
    finally:
        sock.close()
