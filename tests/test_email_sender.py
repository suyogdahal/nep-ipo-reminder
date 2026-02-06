from email.message import EmailMessage

from pipeline import send_email


class DummySMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.logged_in = False
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        return None

    def login(self, user, password):
        self.logged_in = True

    def send_message(self, msg: EmailMessage):
        self.sent.append(msg)


def test_send_email_builds_calendar_message(monkeypatch):
    smtp = DummySMTP("smtp.example.com", 587)

    def fake_smtp(host, port):
        return smtp

    monkeypatch.setattr("pipeline.smtplib.SMTP", fake_smtp)

    send_email(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_pass="pass",
        sender_email="sender@example.com",
        sender_name="Sender",
        recipient="to@example.com",
        subject="Test",
        body="Text",
        html="<p>HTML</p>",
        ics="BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
    )

    assert smtp.logged_in is True
    assert len(smtp.sent) == 1
    msg = smtp.sent[0]
    assert msg["X-MS-OLK-FORCEINSPECTOROPEN"] == "TRUE"
    # Confirm there's a calendar part
    assert any(part.get_content_type() == "text/calendar" for part in msg.walk())
