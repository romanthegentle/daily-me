"""Email delivery over SMTP, configured with environment variables."""

from __future__ import annotations

import os
import smtplib
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from .models import Edition


@dataclass
class EmailSettings:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipients: list[str]
    use_ssl: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> EmailSettings:
        """Read DAILYME_SMTP_* and DAILYME_EMAIL_* settings. Raises ValueError if incomplete."""
        env = os.environ if env is None else env
        missing = [name for name in ("DAILYME_SMTP_HOST", "DAILYME_EMAIL_TO") if not env.get(name)]
        if missing:
            raise ValueError("email isn't set up: " + ", ".join(missing) + " missing (see README)")
        port = int(env.get("DAILYME_SMTP_PORT") or 587)
        username = env.get("DAILYME_SMTP_USER", "")
        sender = env.get("DAILYME_EMAIL_FROM") or username
        if not sender:
            raise ValueError("email isn't set up: set DAILYME_EMAIL_FROM (see README)")
        recipients = [address.strip() for address in env["DAILYME_EMAIL_TO"].split(",")]
        return cls(
            host=env["DAILYME_SMTP_HOST"],
            port=port,
            username=username,
            password=env.get("DAILYME_SMTP_PASSWORD", ""),
            sender=sender,
            recipients=[address for address in recipients if address],
            use_ssl=port == 465 or env.get("DAILYME_SMTP_SSL") == "1",
        )


def subject_for(edition: Edition, template: str) -> str:
    day = date.fromisoformat(edition.date)
    return template.format(
        paper=edition.paper_name,
        weekday=f"{day:%A}",
        day=day.day,
        month=f"{day:%B}",
        year=day.year,
        number=edition.number,
    )


def build_message(
    edition: Edition,
    settings: EmailSettings,
    *,
    subject: str,
    html: str,
    text: str,
    attachment: Path | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender
    message["To"] = ", ".join(settings.recipients)
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    if attachment is not None:
        message.add_attachment(
            attachment.read_bytes(), maintype="application", subtype="pdf", filename=attachment.name
        )
    return message


def send_message(message: EmailMessage, settings: EmailSettings) -> None:
    context = ssl.create_default_context()
    if settings.use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.host, settings.port, context=context, timeout=60
        )
    else:
        server = smtplib.SMTP(settings.host, settings.port, timeout=60)
        server.starttls(context=context)
    with server:
        if settings.username:
            server.login(settings.username, settings.password)
        server.send_message(message)
