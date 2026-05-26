"""
NotificationService — email, Slack, Teams alerts after indexing runs.
Extracted from core/checker.py for single-responsibility.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)


class NotificationService:
    """Send run-completion notifications via email, Slack, or Teams.

    Usage::

        svc = NotificationService(cfg)
        svc.notify_all(counts, total, html_path)
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg = cfg
        self._webhook_timeout = cfg.get("timings", {}).get("webhook_timeout_secs", 10)

    # ── Public ────────────────────────────────────────────────────────────────

    def notify_all(self, counts: dict, total: int, html_path: Path) -> None:
        indexed = counts.get("Indexed", 0)
        not_indexed = counts.get("Not Indexed", 0)
        pct = round(indexed / total * 100, 1) if total else 0
        subject = f"Indexing Report — {indexed}/{total} indexed ({pct}%)"
        body = f"""
        <h2>Indexing Report</h2>
        <p><b>Total checked:</b> {total}</p>
        <p style="color:green"><b>Indexed:</b> {indexed} ({pct}%)</p>
        <p style="color:red"><b>Not Indexed:</b> {not_indexed}</p>
        <p>Full report: {html_path}</p>
        """
        msg = (f"*Indexing Report* — ✅ {indexed} indexed | ❌ {not_indexed} not indexed "
               f"| Total: {total} ({pct}%)")
        self.send_email(subject, body)
        self.send_slack(msg)
        self.send_teams(msg)

    def send_email(self, subject: str, html_body: str,
                   report_path: Path | None = None) -> None:
        cfg = self._cfg.get("email", {})
        if not cfg.get("enabled"):
            return
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = cfg["from"]
            msg["To"] = ", ".join(cfg["to"])
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
                s.starttls()
                s.login(cfg["username"], cfg["password"])
                s.sendmail(cfg["from"], cfg["to"], msg.as_string())
            logger.info("Email sent ✓")
        except Exception as e:
            logger.warning("Email failed: %s", e)

    def send_email_to(self, recipient: str, subject: str, html_body: str) -> bool:
        """Send an email to a single ad-hoc recipient (used by auth flows).

        Distinct from ``send_email`` which goes to the configured ``cfg["to"]``
        notification list. Returns True on apparent success, False on any
        error or when email is disabled in config.
        """
        cfg = self._cfg.get("email", {})
        if not cfg.get("enabled"):
            logger.info("Email disabled in config — skipping ad-hoc send to %s", recipient)
            return False
        if not recipient or "@" not in recipient:
            logger.warning("send_email_to: invalid recipient %r", recipient)
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = cfg["from"]
            msg["To"] = recipient
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
                s.starttls()
                s.login(cfg["username"], cfg["password"])
                s.sendmail(cfg["from"], [recipient], msg.as_string())
            logger.info("Ad-hoc email sent to %s ✓", recipient)
            return True
        except Exception as e:
            logger.warning("Ad-hoc email to %s failed: %s", recipient, e)
            return False

    def send_slack(self, message: str) -> None:
        cfg = self._cfg.get("slack", {})
        if not cfg.get("enabled") or not cfg.get("webhook_url"):
            return
        try:
            from core.security import validate_public_url
            validate_public_url(cfg["webhook_url"])
            import requests
            requests.post(cfg["webhook_url"], json={"text": message},
                          timeout=self._webhook_timeout)
            logger.info("Slack notification sent ✓")
        except Exception as e:
            logger.warning("Slack failed: %s", e)

    def send_teams(self, message: str) -> None:
        cfg = self._cfg.get("teams", {})
        if not cfg.get("enabled") or not cfg.get("webhook_url"):
            return
        try:
            from core.security import validate_public_url
            validate_public_url(cfg["webhook_url"])
            import requests
            requests.post(cfg["webhook_url"], json={"text": message},
                          timeout=self._webhook_timeout)
            logger.info("Teams notification sent ✓")
        except Exception as e:
            logger.warning("Teams failed: %s", e)
