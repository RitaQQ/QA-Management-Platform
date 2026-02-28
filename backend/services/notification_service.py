"""
Notification service — email and webhook alerts for API health events.

Replaces the legacy print-based notification with proper email (SMTP)
and webhook (HTTP POST) delivery.  All external calls are gated behind
configuration checks so that the application never crashes when SMTP
or webhooks are not configured.
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

from database.models import Organization
from middleware.tenant import get_tenant_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SMTP configuration (from environment variables)
# ---------------------------------------------------------------------------

SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('SMTP_FROM', 'noreply@qaplatform.com')

# Notification threshold — number of consecutive errors before alerting
NOTIFICATION_THRESHOLD = int(os.environ.get('NOTIFICATION_THRESHOLD', '3'))


# ---------------------------------------------------------------------------
# Low-level delivery helpers
# ---------------------------------------------------------------------------

def send_email(to_email, subject, body):
    """Send an HTML email notification via SMTP.

    Returns ``True`` on success, ``False`` on failure or if SMTP is not
    configured.  Never raises — errors are logged instead.
    """
    if not SMTP_HOST:
        logger.warning(
            "SMTP not configured. Would send to %s: %s", to_email, subject,
        )
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


def send_webhook(webhook_url, payload):
    """POST a JSON payload to *webhook_url*.

    Returns ``True`` when the remote server responds with a 2xx/3xx status,
    ``False`` otherwise.  Never raises.
    """
    if not webhook_url:
        return False

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        logger.info(
            "Webhook sent to %s: %s", webhook_url, resp.status_code,
        )
        return resp.status_code < 400
    except Exception as exc:
        logger.error("Failed to send webhook to %s: %s", webhook_url, exc)
        return False


# ---------------------------------------------------------------------------
# High-level notification dispatchers
# ---------------------------------------------------------------------------

def notify_api_unhealthy(db, endpoint):
    """Send notifications when an API endpoint becomes unhealthy.

    Looks up the current tenant's ``Organization`` to determine the
    notification email and/or webhook URL.
    """
    org = db.query(Organization).filter_by(id=get_tenant_id()).first()
    if not org:
        return

    subject = f"[QA Platform] API Alert: {endpoint.name} is unhealthy"
    body = f"""
    <h2>API Health Alert</h2>
    <p><strong>API Name:</strong> {endpoint.name}</p>
    <p><strong>URL:</strong> {endpoint.url}</p>
    <p><strong>Status:</strong> Unhealthy</p>
    <p><strong>Error Count:</strong> {endpoint.error_count}</p>
    <p><strong>Last Error:</strong> {endpoint.last_error or 'N/A'}</p>
    <p><strong>Organization:</strong> {org.name}</p>
    """

    # Send email if configured
    if org.notification_email:
        send_email(org.notification_email, subject, body)

    # Send webhook if configured
    if org.notification_webhook_url:
        payload = {
            'event': 'api_unhealthy',
            'api_name': endpoint.name,
            'api_url': endpoint.url,
            'status': 'unhealthy',
            'error_count': endpoint.error_count,
            'error': endpoint.last_error,
            'organization': org.name,
        }
        send_webhook(org.notification_webhook_url, payload)


def notify_api_recovered(db, endpoint):
    """Send notifications when an API endpoint recovers from unhealthy state."""
    org = db.query(Organization).filter_by(id=get_tenant_id()).first()
    if not org:
        return

    subject = f"[QA Platform] API Recovered: {endpoint.name} is healthy"
    body = f"""
    <h2>API Recovery Notice</h2>
    <p><strong>API Name:</strong> {endpoint.name}</p>
    <p><strong>URL:</strong> {endpoint.url}</p>
    <p><strong>Status:</strong> Healthy (Recovered)</p>
    <p><strong>Organization:</strong> {org.name}</p>
    """

    if org.notification_email:
        send_email(org.notification_email, subject, body)

    if org.notification_webhook_url:
        payload = {
            'event': 'api_recovered',
            'api_name': endpoint.name,
            'api_url': endpoint.url,
            'status': 'healthy',
            'organization': org.name,
        }
        send_webhook(org.notification_webhook_url, payload)
