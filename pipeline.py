#!/usr/bin/env python3
import argparse
import hashlib
import hmac
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

import requests
from dotenv import load_dotenv

from scrape_open_issues import fetch_all_open_issues


LEDGER_PATH = Path("data/sent_ledger.json")
DEFAULT_FROM_NAME = "IPO Alerts"
DEFAULT_FROM_EMAIL = "noreply@example.com"
NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))


def log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fold_ics(ics: str, limit: int = 70) -> str:
    lines = ics.split("\r\n")
    folded = []
    for line in lines:
        if len(line) <= limit:
            folded.append(line)
            continue
        while len(line) > limit:
            folded.append(line[:limit])
            line = " " + line[limit:]
        folded.append(line)
    return "\r\n".join(folded)


def issue_id_from_row(row: Dict[str, str]) -> str:
    symbol = (row.get("Symbol") or "").strip()
    opening = (row.get("Opening Date") or "").strip()
    if not symbol or not opening:
        raise ValueError("Missing Symbol or Opening Date.")
    return f"{symbol}|{opening}"


def load_ledger() -> Dict[str, Dict[str, str]]:
    if not LEDGER_PATH.exists():
        return {}
    with LEDGER_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_ledger(ledger: Dict[str, Dict[str, str]]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2, sort_keys=True)


def prune_ledger(ledger: Dict[str, Dict[str, str]], days: int = 90) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for issue_id in list(ledger.keys()):
        entries = ledger.get(issue_id, {})
        for key in list(entries.keys()):
            try:
                ts = datetime.fromisoformat(entries[key])
            except ValueError:
                del entries[key]
                continue
            if ts < cutoff:
                del entries[key]
        if not entries:
            del ledger[issue_id]


def hmac_hash(salt: str, value: str) -> str:
    digest = hmac.new(salt.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def fetch_brevo_contacts(api_key: str, list_id: str, verbose: bool) -> List[Dict[str, str]]:
    headers = {"api-key": api_key, "accept": "application/json"}
    contacts = []
    limit = 500
    offset = 0
    while True:
        url = f"https://api.brevo.com/v3/contacts/lists/{list_id}/contacts"
        resp = requests.get(url, headers=headers, params={"limit": limit, "offset": offset}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("contacts", [])
        contacts.extend(batch)
        log(f"Fetched {len(batch)} contacts (offset={offset}).", verbose)
        if len(batch) < limit:
            break
        offset += limit
    return contacts


def build_ics(
    row: Dict[str, str],
    issue_id: str,
    recipient: str,
    organizer_email: str,
    organizer_name: str,
) -> str:
    closing = parse_iso_date(row["Closing Date"])
    start_local = datetime.combine(closing, datetime.min.time(), tzinfo=NEPAL_TZ).replace(
        hour=9, minute=0
    )
    end_local = start_local + timedelta(hours=1)
    start_utc = start_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_utc = end_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    uid = hashlib.sha256(issue_id.encode("utf-8")).hexdigest()
    summary = ics_escape(
        f"Final Day: {row.get('Type', 'IPO')} {row.get('Company', '')} ({row.get('Symbol', '')})"
    )
    description = ics_escape(
        f"Final day to apply (9:00–10:00 AM NPT reminder).\\n"
        f"Close: {row.get('Closing Date', '')}\\n"
        f"Issue Manager: {row.get('Issue Manager', '')}"
    )

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//nep-ipo-reminder//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"ORGANIZER;CN={ics_escape(organizer_name)}:mailto:{organizer_email}",
        f"ATTENDEE;CN={ics_escape(recipient)};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{recipient}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"DTSTART:{start_utc}",
        f"DTEND:{end_utc}",
        "SEQUENCE:0",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    ics = "\r\n".join(lines) + "\r\n"
    return fold_ics(ics)


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    sender_email: str,
    sender_name: str,
    recipient: str,
    subject: str,
    body: str,
    html: str,
    ics: str,
):
    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Content-Class"] = "urn:content-classes:calendarmessage"
    msg["X-MS-OLK-FORCEINSPECTOROPEN"] = "TRUE"
    msg.set_content(body)
    msg.add_alternative(html, subtype="html")
    msg.add_alternative(
        ics,
        subtype="calendar",
        params={"method": "REQUEST", "charset": "UTF-8"},
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


DEFAULT_TYPE_IDS = [1, 2, 3]  # IPO, FPO, Right Share
DEV_EMAIL = "suyoginusa@gmail.com"


def run_pipeline(verbose: bool, force_send: bool, dev_mode: bool) -> int:
    load_dotenv()

    brevo_api_key = os.getenv("BREVO_API_KEY")
    brevo_list_id = os.getenv("BREVO_LIST_ID")
    smtp_host = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
    smtp_port = int(os.getenv("BREVO_SMTP_PORT", "587"))
    smtp_user = os.getenv("BREVO_SMTP_USER")
    smtp_pass = os.getenv("BREVO_SMTP_PASS")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", DEFAULT_FROM_EMAIL)
    sender_name = os.getenv("BREVO_SENDER_NAME", DEFAULT_FROM_NAME)
    dedupe_salt = os.getenv("DEDUPE_SALT")

    missing = [k for k, v in {
        "BREVO_API_KEY": brevo_api_key,
        "BREVO_LIST_ID": brevo_list_id,
        "BREVO_SMTP_USER": smtp_user,
        "BREVO_SMTP_PASS": smtp_pass,
        "DEDUPE_SALT": dedupe_salt,
    }.items() if not v]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    open_rows = fetch_all_open_issues(verbose, DEFAULT_TYPE_IDS)
    log(f"Open rows: {len(open_rows)}", verbose)

    if not open_rows:
        return 0

    contacts = fetch_brevo_contacts(brevo_api_key, brevo_list_id, verbose)
    total_contacts = len(contacts)
    emails = [c.get("email") for c in contacts if c.get("email")]
    log(f"Contacts fetched: {total_contacts}", verbose)
    log(f"Recipients: {len(emails)}", verbose)

    if dev_mode:
        emails = [DEV_EMAIL]
        log(f"Dev mode enabled: sending only to {DEV_EMAIL}", verbose)

    ledger = {}
    if not dev_mode:
        ledger = load_ledger()
        prune_ledger(ledger, days=90)
    sent_count = 0

    for row in open_rows:
        try:
            issue_id = issue_id_from_row(row)
        except ValueError as exc:
            log(f"Skipping row: {exc}", verbose)
            continue

        if not row.get("Closing Date"):
            log(f"Skipping {issue_id}: missing Closing Date", verbose)
            continue

        issue_bucket = ledger.setdefault(issue_id, {})
        subject = f"Final Day: {row.get('Type', 'IPO')} {row.get('Company', '')} ({row.get('Symbol', '')})"
        body = (
            f"Final day to apply for {row.get('Company', '')} ({row.get('Symbol', '')}).\n\n"
            f"Reminder time: 9:00–10:00 AM NPT\n"
            f"Type: {row.get('Type', '')}\n"
            f"Close: {row.get('Closing Date', '')}\n"
            f"Issue Manager: {row.get('Issue Manager', '')}\n"
        )
        html = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background:#f6f7fb; padding:24px;">
    <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;padding:24px;border:1px solid #e6e8ef;">
      <div style="font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;">
        {row.get('Type','IPO')} OPEN
      </div>
      <h1 style="font-size:22px;margin:0 0 12px 0;color:#111827;">
        {row.get('Company','')} ({row.get('Symbol','')})
      </h1>
      <p style="font-size:15px;color:#374151;line-height:1.5;margin:0 0 16px 0;">
        Final day to apply. Your calendar reminder is set for 9:00–10:00 AM NPT.
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;color:#111827;">
        <tr><td style="padding:8px 0;color:#6b7280;">Close</td><td style="padding:8px 0;">{row.get('Closing Date','')}</td></tr>
        <tr><td style="padding:8px 0;color:#6b7280;">Reminder</td><td style="padding:8px 0;">9:00–10:00 AM NPT</td></tr>
        <tr><td style="padding:8px 0;color:#6b7280;">Issue Manager</td><td style="padding:8px 0;">{row.get('Issue Manager','')}</td></tr>
        <tr><td style="padding:8px 0;color:#6b7280;">Type</td><td style="padding:8px 0;">{row.get('Type','')}</td></tr>
      </table>
      <p style="font-size:12px;color:#9ca3af;margin-top:16px;">
        You’re receiving this because you subscribed to IPO alerts.
      </p>
    </div>
  </body>
</html>
"""

        for email in emails:
            ics = build_ics(row, issue_id, email, sender_email, sender_name)
            if os.getenv("DUMP_ICS") == "1":
                Path("data").mkdir(parents=True, exist_ok=True)
                Path("data/last_invite.ics").write_text(ics, encoding="utf-8")
            dedupe_key = hmac_hash(dedupe_salt, f"{email}|{issue_id}")
            if not (dev_mode or force_send) and dedupe_key in issue_bucket:
                continue

            send_email(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user,
                smtp_pass=smtp_pass,
                sender_email=sender_email,
                sender_name=sender_name,
                recipient=email,
                subject=subject,
                body=body,
                html=html,
                ics=ics,
            )
            if not dev_mode:
                issue_bucket[dedupe_key] = datetime.now(timezone.utc).isoformat()
            sent_count += 1

    if sent_count and not dev_mode:
        save_ledger(ledger)

    log(f"Sent {sent_count} emails.", verbose)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run IPO alert pipeline.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--force-send",
        action="store_true",
        help="Send even if already recorded in ledger (for testing).",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Dev mode: send only to a single test email and bypass dedupe.",
    )
    parser.add_argument(
        "--dump-ics",
        action="store_true",
        help="Write the last generated ICS to data/last_invite.ics.",
    )
    args = parser.parse_args()
    os.environ["DUMP_ICS"] = "1" if args.dump_ics else "0"
    return run_pipeline(args.verbose, args.force_send, args.dev)


if __name__ == "__main__":
    raise SystemExit(main())
