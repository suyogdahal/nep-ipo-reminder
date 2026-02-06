from pipeline import build_ics


def test_build_ics_final_day_window():
    row = {
        "Type": "IPO",
        "Company": "Hotel Forest Inn Limited",
        "Symbol": "HFIL",
        "Opening Date": "2026-02-05",
        "Closing Date": "2026-02-09",
        "Issue Manager": "NIC Asia Capital Limited",
    }
    issue_id = "HFIL|2026-02-05"
    ics = build_ics(
        row=row,
        issue_id=issue_id,
        recipient="test@example.com",
        organizer_email="sender@example.com",
        organizer_name="Sender",
    )

    assert "SUMMARY:Final Day: IPO Hotel Forest Inn Limited (HFIL)" in ics
    assert "DTSTART:20260209T031500Z" in ics  # 09:00 NPT
    assert "DTEND:20260209T041500Z" in ics    # 10:00 NPT
