import types
import pytest

import publishers.wiley_library as wl


def test_clean_doi():
    assert wl.clean_doi(None) is None
    assert wl.clean_doi("10.1002/xyz") == "10.1002/xyz"
    # Decorated/annotated DOIs should be cleaned
    assert wl.clean_doi("10.1002/abc@v1") == "10.1002/abc"


def test_format_author_name():
    assert wl.format_author_name("Doe, Jane") == "Doe Jane"
    assert wl.format_author_name("Jane Doe") == "Jane Doe"


def test_get_pdf_content_for_wiley_detects_pdf(monkeypatch):
    # Minimal fake response object
    class FakeResp:
        def __init__(self, status=200, content=b"%PDF-1.4 bytes", ctype="application/pdf", url="https://x"):
            self.status_code = status
            self.content = content
            self.headers = {"Content-Type": ctype}
            self.url = url

    class FakeSession:
        def __init__(self, resp):
            self._resp = resp
        def get(self, url, headers=None, timeout=30, allow_redirects=True):
            return self._resp

    # Make cloudscraper.create_scraper() return our fake session
    monkeypatch.setattr(wl.cloudscraper, "create_scraper", lambda **kw: FakeSession(FakeResp()))

    content = wl.get_pdf_content_for_wiley(doi="10.1002/xyz", landing_url="https://example.org/landing")
    assert isinstance(content, (bytes, bytearray))
    assert content.startswith(b"%PDF")


def test_process_wiley_library_happy_path(monkeypatch, tmp_path):
    """
    No network, no DB:
    - mock _fetch_wiley_page to return one synthetic record and no next page
    - mock is_openaccess_pdf to True
    - mock get_pdf_content_for_wiley to return valid PDF bytes
    - mock extract_principal_author_and_email to return a name/email
    - mock save_pdf to capture filename
    """
    # One synthetic "record" node
    monkeypatch.setattr(wl, "_fetch_wiley_page", lambda *a, **k: ([object()], None))
    # Normalised dict that process_wiley_library expects
    monkeypatch.setattr(wl, "_normalise_record", lambda n: {
        "doi": "10.1002/xyz",
        "title": "A Minimal Test Title",
        "landing_url": "https://example.org/landing",
        "subjects": ["climate"],
        "published_date": "2023-01-01",
        "issued_year": None,
    })
    monkeypatch.setattr(wl, "is_openaccess_pdf", lambda doi, timeout=30: True)
    monkeypatch.setattr(wl, "get_pdf_content_for_wiley", lambda doi, landing_url=None: b"%PDF-1.4 bytes")
    monkeypatch.setattr(wl, "extract_principal_author_and_email", lambda b: ("Jane Doe", "jane@example.com"))

    saved = {}
    def fake_save(pdf_name, pdf_content):
        saved["pdf_name"] = pdf_name
        out = tmp_path / pdf_name
        out.write_bytes(pdf_content)
        return str(out)

    monkeypatch.setattr(wl, "save_pdf", fake_save)

    processed, total, next_page = wl.process_wiley_library(keywords=["climate"], start_page=1)

    # Assertions
    assert total == 1
    assert len(processed) == 1
    rec = processed[0]
    assert rec["doi"] == "10.1002/xyz"
    assert rec["author_email"] == "jane@example.com"
    assert rec["title"] == "A Minimal Test Title"
    assert "calc_hash" in rec
    assert saved["pdf_name"].startswith(wl.PUBLISHER_NAME_FOR_DB)
