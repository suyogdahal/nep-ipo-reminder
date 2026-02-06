#!/usr/bin/env python3
import argparse
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from dotenv import load_dotenv


NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))


def ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(
    summary: str,
    description: str,
    start_date: str,
    end_date: str,
    organizer_email: str,
    organizer_name: str,
    attendee_email: str,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"test-{int(datetime.now().timestamp())}@nep-ipo-reminder"
    start_local = datetime.strptime(start_date, "%Y%m%d").replace(tzinfo=NEPAL_TZ)
    end_local = datetime.strptime(end_date, "%Y%m%d").replace(tzinfo=NEPAL_TZ)
    start_utc = start_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_utc = end_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//nep-ipo-reminder//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{now}\r\n"
        f"ORGANIZER;CN={ics_escape(organizer_name)}:mailto:{organizer_email}\r\n"
        f"ATTENDEE;CN={ics_escape(attendee_email)};ROLE=REQ-PARTICIPANT;"
        f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee_email}\r\n"
        f"SUMMARY:{ics_escape(summary)}\r\n"
        f"DESCRIPTION:{ics_escape(description)}\r\n"
        f"DTSTART:{start_utc}\r\n"
        f"DTEND:{end_utc}\r\n"
        "SEQUENCE:0\r\n"
        "STATUS:CONFIRMED\r\n"
        "TRANSP:OPAQUE\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics


def send_calendar_test(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    sender_email: str,
    sender_name: str,
    recipient: str,
):
    summary = "Test IPO Event: Calendar Rendering Check"
    description = "This is a test invite to validate Gmail calendar rendering."
    start = (datetime.now(NEPAL_TZ).date() + timedelta(days=1)).strftime("%Y%m%d")
    end = (datetime.now(NEPAL_TZ).date() + timedelta(days=2)).strftime("%Y%m%d")

    ics = build_ics(
        summary=summary,
        description=description,
        start_date=start,
        end_date=end,
        organizer_email=sender_email,
        organizer_name=sender_name,
        attendee_email=recipient,
    )

    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient
    msg["Subject"] = summary

    text_body = "If you can read this, please open the calendar invite attachment."
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif;">
        <h2>{summary}</h2>
        <p>This is a test invite to validate calendar rendering in Gmail.</p>
        <p>Dates: {start} to {end}</p>
      </body>
    </html>
    """

    msg["Content-Class"] = "urn:content-classes:calendarmessage"
    msg["X-MS-OLK-FORCEINSPECTOROPEN"] = "TRUE"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    msg.add_alternative(
        ics,
        subtype="calendar",
        params={"method": "REQUEST", "charset": "UTF-8"},
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Send a test calendar invite.")
    parser.add_argument("--to", default="suyoginusa@gmail.com", help="Recipient email")
    args = parser.parse_args()

    smtp_host = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
    smtp_port = int(os.getenv("BREVO_SMTP_PORT", "587"))
    smtp_user = os.getenv("BREVO_SMTP_USER")
    smtp_pass = os.getenv("BREVO_SMTP_PASS")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "IPO Alerts")

    missing = [k for k, v in {
        "BREVO_SMTP_USER": smtp_user,
        "BREVO_SMTP_PASS": smtp_pass,
        "BREVO_SENDER_EMAIL": sender_email,
    }.items() if not v]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        return 2

    send_calendar_test(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        sender_email=sender_email,
        sender_name=sender_name,
        recipient=args.to,
    )
    print(f"Sent test invite to {args.to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
