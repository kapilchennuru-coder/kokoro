"""Telephony health checks for Asterisk AMI — never pretend calls succeed."""

from __future__ import annotations

import os
import socket

from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASTERISK_ENV_PATH = os.path.join(BASE_DIR, "..", "asterisk", ".env")


def check_telephony() -> dict:
    env = dotenv_values(ASTERISK_ENV_PATH)
    ami_user = env.get("AMI_USERNAME") or ""
    ami_secret = env.get("AMI_SECRET") or ""
    host = os.environ.get("AMI_HOST", "localhost")
    port = int(os.environ.get("AMI_PORT", "5038"))

    if not ami_user or not ami_secret:
        return {
            "available": False,
            "configured": False,
            "reachable": False,
            "detail": "Calling is not available right now. Please try again later.",
            "host": host,
            "port": port,
        }

    reachable = False
    detail = "Ready"
    try:
        with socket.create_connection((host, port), timeout=2) as sock:
            banner = sock.recv(1024).decode("utf-8", errors="ignore")
            reachable = "Asterisk" in banner or "Manager" in banner or bool(banner)
            if not reachable:
                detail = "Calling is not available right now. Please try again later."
            else:
                detail = "Ready"
    except OSError:
        return {
            "available": False,
            "configured": True,
            "reachable": False,
            "detail": "Calling is not available right now. Please try again later.",
            "host": host,
            "port": port,
        }

    return {
        "available": reachable,
        "configured": True,
        "reachable": reachable,
        "detail": detail,
        "host": host,
        "port": port,
    }
