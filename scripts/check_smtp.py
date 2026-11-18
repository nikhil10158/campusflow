import smtplib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.services.mailer import build_message

settings = get_settings()
if not (settings.smtp_user and settings.smtp_pass):
    print("SMTP_USER or SMTP_PASS is empty in backend/.env, so email is switched off.")
    sys.exit(1)

target = settings.smtp_redirect_to or settings.smtp_user
message = build_message(target, "CampusFlow email check", "If you can read this, Gmail SMTP works and CampusFlow can send email.", [("Server", f"{settings.smtp_host}:{settings.smtp_port}"), ("Sender", settings.smtp_from)])
try:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_pass)
        server.send_message(message)
except smtplib.SMTPAuthenticationError:
    print("Gmail rejected the login. Check SMTP_USER and use a 16-character App Password, not your normal password. Turn on 2-Step Verification if the App Passwords page is missing.")
    sys.exit(1)
except (OSError, smtplib.SMTPException) as problem:
    print(f"Could not send: {problem}")
    print("If this says timed out or unreachable, your network or firewall may block port 587. Try another network.")
    sys.exit(1)
print(f"Sent. Check the inbox of {target} (and the spam folder).")
