import os
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List


@dataclass(frozen=True)
class GmailCredentials:
    user: str
    app_password: str
    recipients: List[str]


def load_credentials() -> GmailCredentials:
    user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    recipients = [r.strip() for r in os.environ.get("RECIPIENT_EMAIL", "").split(",") if r.strip()]
    missing = [name for name, value in (("GMAIL_USER", user), ("GMAIL_APP_PASSWORD", password),
                                        ("RECIPIENT_EMAIL", recipients)) if not value]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    return GmailCredentials(user, password, recipients)


def build_message(subject: str, html: str, text: str, sender: str, recipients: List[str]) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    # Order matters: clients display the last part they support
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def send_email(subject: str, html: str, text: str, creds: GmailCredentials, email_cfg: Dict[str, Any]) -> None:
    msg = build_message(subject, html, text, creds.user, creds.recipients)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(email_cfg["smtp_host"], int(email_cfg["smtp_port"]), context=context, timeout=30) as smtp:
        smtp.login(creds.user, creds.app_password)
        smtp.sendmail(creds.user, creds.recipients, msg.as_string())
