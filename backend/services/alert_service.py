"""
Email Alert Service for SatQuery AI.
Sends real email alerts via SMTP. Never fabricates email delivery.
Credentials must be configured via environment variables (SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, ALERT_FROM_EMAIL).
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from backend.config import get_settings

logger = logging.getLogger(__name__)


def send_email(to_address: str, subject: str, body: str) -> bool:
    """
    Send a real email via SMTP.
    Returns True on success, False if SMTP is unconfigured.
    Raises an exception with details if delivery fails.
    """
    settings = get_settings()
    username = settings.SMTP_USER or settings.SMTP_USERNAME
    from_addr = settings.ALERT_FROM_EMAIL or settings.SMTP_FROM or username

    if not settings.SMTP_HOST or not username or not settings.SMTP_PASSWORD:
        logger.warning(f"SMTP not configured. Cannot send email to {to_address}")
        return False

    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_address

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20.0) as server:
            server.starttls()
            server.login(username, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email alert successfully delivered to {to_address}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_address}: {e}")
        raise Exception(f"SMTP Email delivery failed: {str(e)}")
