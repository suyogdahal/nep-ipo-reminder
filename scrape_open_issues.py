#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "https://www.sharesansar.com/existing-issues"
DEFAULT_OUT = "./open_issues.json"
DEFAULT_TYPE = 1
TYPE_CONFIG = {
    1: {"tab": "#ipo", "table": "#myTableEip", "name": "IPO"},
    2: {"tab": "#fpo", "table": "#myTableEfp", "name": "FPO"},
    3: {"tab": "#rightshare", "table": "#myTableErs", "name": "Right Share"},
    4: {"tab": "#mutualfund", "table": "#myTableEmf", "name": "Mutual Fund"},
    5: {"tab": "#ipolocal", "table": "#myTableEipl", "name": "IPO-Local"},
    7: {"tab": "#bondsAndDeb", "table": "#myTableEbd", "name": "Bonds/Debentures"},
    8: {"tab": "#ipomigrant", "table": "#myTableEim", "name": "IPO to Migrant Workers"},
    9: {"tab": "#ipoqiis", "table": "#myTableQiis", "name": "IPO for QIIs"},
}


def log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def extract_table(page, table_selector: str):
    header_cells = page.locator(f"{table_selector} thead tr th")
    headers = [header_cells.nth(i).inner_text().strip() for i in range(header_cells.count())]

    rows = []
    body_rows = page.locator(f"{table_selector} tbody tr")
    for r in range(body_rows.count()):
        row = body_rows.nth(r)
        cells = row.locator("td")
        values = [cells.nth(i).inner_text().strip() for i in range(cells.count())]
        if not values:
            continue
        row_obj = {}
        for idx, header in enumerate(headers):
            row_obj[header] = values[idx] if idx < len(values) else ""
        rows.append(row_obj)
    return headers, rows


def fetch_open_issues(type_id: int, verbose: bool):
    config = TYPE_CONFIG.get(type_id)
    if not config:
        raise ValueError(f"Unsupported type: {type_id}")

    tab_selector = config["tab"]
    table_selector = config["table"]
    type_name = config["name"]

    log(f"Launching browser and loading {URL} (type={type_id}) ...", verbose)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")

        # Click the tab if it's not the default (IPO).
        if tab_selector != "#ipo":
            page.locator(f"a[href='{tab_selector}']").click()

        # Wait for data rows to render.
        page.wait_for_selector(f"{table_selector} tbody tr", timeout=30000)

        headers, rows = extract_table(page, table_selector)
        browser.close()

    status_key = None
    for header in headers:
        if header.strip().lower() == "status":
            status_key = header
            break
    if status_key is None:
        raise ValueError("Status column not found in table headers.")

    open_rows = [row for row in rows if row.get(status_key, "").strip().lower() == "open"]
    for row in open_rows:
        row["Type"] = type_name
        row["TypeId"] = type_id
    return open_rows


def fetch_all_open_issues(verbose: bool, type_ids=None):
    if type_ids is None:
        type_ids = sorted(TYPE_CONFIG.keys())
    open_rows = []
    for type_id in type_ids:
        open_rows.extend(fetch_open_issues(type_id, verbose))
    return open_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape ShareSansar existing issues and filter Status=Open."
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Output JSON file path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--type",
        type=int,
        default=DEFAULT_TYPE,
        help="Issue type (1=IPO, 2=FPO, 3=Right Share, 4=Mutual Fund, 5=IPO-Local, 7=Bonds/Debentures, 8=IPO to Migrant Workers, 9=IPO for QIIs)",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Fetch all supported issue types and include Type/TypeId in output.",
    )
    args = parser.parse_args()

    try:
        if args.all_types:
            open_rows = fetch_all_open_issues(args.verbose)
        else:
            open_rows = fetch_open_issues(args.type, args.verbose)
    except Exception as exc:
        print(f"Scrape error: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(open_rows, f, ensure_ascii=False, indent=2)

    log(f"Found {len(open_rows)} open rows.", args.verbose)
    log(f"Wrote {out_path}.", args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
