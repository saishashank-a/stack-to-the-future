"""Email notifications."""
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
