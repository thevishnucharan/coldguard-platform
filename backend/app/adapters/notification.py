from typing import Protocol
import logging
import smtplib
from email.message import EmailMessage
import os

logger = logging.getLogger(__name__)

class NotificationProvider(Protocol):
    def send(self, recipient: str, subject: str, message: str) -> bool:
        """Sends a notification to the specified recipient."""
        ...

class ConsoleNotificationProvider:
    def send(self, recipient: str, subject: str, message: str) -> bool:
        logger.info(f"\n{'='*40}\n[SIMULATED NOTIFICATION to {recipient}]\nSubject: {subject}\n\n{message}\n{'='*40}\n")
        return True

class EmailNotificationProvider:
    def __init__(self):
        self.host = os.getenv("SMTP_HOST")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASSWORD")
        self.is_configured = bool(self.host and self.user and self.password)
        self.console_fallback = ConsoleNotificationProvider()

    def send(self, recipient: str, subject: str, message: str) -> bool:
        if not self.is_configured:
            logger.warning("SMTP not configured. Falling back to simulated console email.")
            return self.console_fallback.send(recipient, subject, message)
            
        try:
            msg = EmailMessage()
            msg.set_content(message)
            msg["Subject"] = subject
            msg["From"] = self.user
            msg["To"] = recipient
            
            # Using basic STARTTLS config
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
                
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
