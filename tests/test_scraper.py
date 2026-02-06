from scrape_open_issues import fetch_open_issues


class DummyLocator:
    def __init__(self, values):
        self.values = values

    def count(self):
        return len(self.values)

    def nth(self, idx):
        value = self.values[idx]
        if isinstance(value, DummyRow):
            return value
        return DummyLocator(value)

    def inner_text(self):
        return self.values

    def locator(self, _):
        return self


class DummyRow:
    def __init__(self, row):
        self.row = row

    def locator(self, selector):
        if selector == "td":
            return DummyLocator(self.row)
        return DummyLocator([])

    def count(self):
        return 1

    def nth(self, idx):
        if idx != 0:
            raise IndexError(idx)
        return self


class DummyPage:
    def __init__(self):
        self._headers = ["S.N.", "Symbol", "Company", "Status"]
        self._rows = [
            ["1", "AAA", "Company A", "Closed"],
            ["2", "BBB", "Company B", "Open"],
        ]

    def goto(self, *_args, **_kwargs):
        return None

    def locator(self, selector):
        if "thead" in selector:
            return DummyLocator(self._headers)
        if "tbody tr" in selector:
            return DummyLocator([DummyRow(row) for row in self._rows])
        if selector == "td":
            return DummyLocator(self._rows)
        return DummyLocator([])

    def wait_for_selector(self, *_args, **_kwargs):
        return None


class DummyBrowser:
    def new_page(self):
        return DummyPage()

    def close(self):
        return None


class DummyChromium:
    def launch(self, headless=True):
        return DummyBrowser()


class DummyPlaywright:
    def __init__(self):
        self.chromium = DummyChromium()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_open_issues_filters_open(monkeypatch):
    def fake_playwright():
        return DummyPlaywright()

    monkeypatch.setattr("scrape_open_issues.sync_playwright", fake_playwright)

    rows = fetch_open_issues(1, verbose=False)
    assert len(rows) == 1
    assert rows[0]["Symbol"] == "BBB"
