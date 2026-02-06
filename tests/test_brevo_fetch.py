from pipeline import fetch_brevo_contacts


class DummyResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_brevo_contacts_paginates(monkeypatch):
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["offset"])
        if params["offset"] == 0:
            return DummyResp({"contacts": [{"email": "a@test.com"}] * 500})
        return DummyResp({"contacts": [{"email": "b@test.com"}]})

    monkeypatch.setattr("pipeline.requests.get", fake_get)

    contacts = fetch_brevo_contacts("key", "3", verbose=False)
    assert len(contacts) == 501
    assert calls == [0, 500]
