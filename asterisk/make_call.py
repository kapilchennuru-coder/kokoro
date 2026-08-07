# =============================================================
# TEST / PROTOTYPE ONLY
#
# This is the "Tell Asterisk to call +1XXXXXXXXXX" step in the
# architecture diagram:
#
#   Your App
#     |
#     +-- Generate speech with Kokoro -> reminder.wav
#     |
#     +-- Tell Asterisk to call +1XXXXXXXXXX   <-- THIS SCRIPT
#                     |
#              SIP Trunk Provider (VoIP Office)
#                     |
#              Customer's phone
#
# Connects to Asterisk's AMI (Asterisk Manager Interface) and tells it
# to originate a call to a phone number, then run the play-reminder
# dialplan extension (extensions.conf) once answered, which plays the
# Kokoro-generated audio file.
# =============================================================

import socket
import time

AMI_HOST = "localhost"
AMI_PORT = 5038
AMI_USER = "zebl_ami_user"
AMI_SECRET = "AMI_SECRET"  # must match config/manager.conf


def _send_ami_command(sock, action_lines: list) -> None:
    message = "\r\n".join(action_lines) + "\r\n\r\n"
    sock.sendall(message.encode("utf-8"))


def make_call(destination_number: str, audio_filename_no_extension: str) -> None:
    """
    destination_number: e.g. "+15551234567"
    audio_filename_no_extension: the .wav file's name (without .wav),
        already copied into asterisk/audio/ (mounted to Asterisk's
        custom sounds folder - see docker-compose.yml).
    """
    sock = socket.create_connection((AMI_HOST, AMI_PORT), timeout=10)
    sock.recv(1024)  # AMI's initial banner line

    # Step 1: log in to AMI.
    _send_ami_command(sock, [
        "Action: Login",
        f"Username: {AMI_USER}",
        f"Secret: {AMI_SECRET}",
    ])
    time.sleep(0.5)
    print(sock.recv(4096).decode("utf-8", errors="ignore"))

    # Step 2: originate the call - dial the trunk, and once answered,
    # jump into the play-reminder extension with AUDIO_FILE set so the
    # dialplan knows which patient's audio to play.
    _send_ami_command(sock, [
        "Action: Originate",
        f"Channel: PJSIP/{destination_number}@voipoffice-endpoint",
        "Context: outbound-calls",
        "Exten: play-reminder",
        "Priority: 1",
        f"Variable: AUDIO_FILE={audio_filename_no_extension}",
        "CallerID: Zebl AR <1000>",
        "Timeout: 30000",
    ])
    time.sleep(0.5)
    print(sock.recv(4096).decode("utf-8", errors="ignore"))

    sock.close()


if __name__ == "__main__":
    # Example: call a test number and play patient_1_voice.wav
    # (copy that file into asterisk/audio/ first - see docker-compose.yml)
    make_call("+15551234567", "patient_1_voice")
