"""Optional delivery via Telegram and/or e-mail. DISABLED by default.

Nothing is sent unless DELIVERY_ENABLED=true AND the channel's credentials are set.
Otherwise every call is a dry run that only describes what would be sent.

Environment variables
  DELIVERY_ENABLED     true/false (default false)
  TELEGRAM_BOT_TOKEN   bot token from @BotFather
  TELEGRAM_CHAT_ID     target chat / group id
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD
  EMAIL_FROM, EMAIL_TO (comma separated)
"""

from __future__ import annotations

import json
import mimetypes
import os
import smtplib
import ssl
import urllib.request
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


@dataclass
class DeliveryResult:
    channel: str
    sent: bool
    detail: str


def delivery_enabled() -> bool:
    return os.getenv("DELIVERY_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def email_configured() -> bool:
    return all(os.getenv(k) for k in ("SMTP_HOST", "EMAIL_FROM", "EMAIL_TO"))


def _strip_md(text: str) -> str:
    return text.replace("**", "")


def _multipart(fields: dict, file_field: str, path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def send_telegram(title: str, summary: str, html_path: Path) -> DeliveryResult:
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    base = f"https://api.telegram.org/bot{token}"
    text = f"{title}\n\n{_strip_md(summary)}"[:4000]
    req = urllib.request.Request(f"{base}/sendMessage", method="POST",
                                 data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()  # noqa: S310
    body, ctype = _multipart({"chat_id": chat, "caption": title}, "document", html_path)
    req = urllib.request.Request(f"{base}/sendDocument", data=body, method="POST", headers={"Content-Type": ctype})
    urllib.request.urlopen(req, timeout=60).read()  # noqa: S310
    return DeliveryResult("telegram", True, f"Sent to chat {chat}")


def send_email(title: str, summary: str, html_path: Path) -> DeliveryResult:
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content(_strip_md(summary) + "\n\nThe full report is attached as an HTML file.")
    msg.add_attachment(html_path.read_bytes(), maintype="text", subtype="html", filename=html_path.name)
    host, port = os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        s.send_message(msg)
    return DeliveryResult("email", True, f"Sent to {os.environ['EMAIL_TO']}")


def deliver(title: str, summary: str, html_path: str | Path) -> list[DeliveryResult]:
    """Send the report through every configured channel, or dry-run if disabled."""
    html_path = Path(html_path)
    channels = []
    if telegram_configured():
        channels.append(("telegram", send_telegram))
    if email_configured():
        channels.append(("email", send_email))
    if not delivery_enabled():
        names = ", ".join(c for c, _ in channels) or "no channel configured"
        return [DeliveryResult("dry-run", False,
                               f"DELIVERY_ENABLED is not 'true', nothing was sent ({names}). "
                               f"Would send: '{title}' with {html_path.name} attached")]
    if not channels:
        return [DeliveryResult("none", False, "DELIVERY_ENABLED=true but no Telegram or e-mail credentials are set.")]
    results = []
    for name, fn in channels:
        try:
            results.append(fn(title, summary, html_path))
        except Exception as exc:  # report but don't crash the pipeline
            results.append(DeliveryResult(name, False, f"Failed: {type(exc).__name__}: {exc}"))
    return results
