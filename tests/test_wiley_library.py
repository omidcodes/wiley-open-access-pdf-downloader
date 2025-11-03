import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from publishers.wiley_library import get_pdf_content_for_wiley, process_wiley_library

import pytest
from unittest.mock import patch
from lxml import etree

def test_process_wiley_library_basic(monkeypatch):
    # Import after pytest has set up path
    from publishers.wiley_library import process_wiley_library

    # --- Mock DB layer ---
    monkeypatch.setattr("publishers.wiley_library.select_query.get_records", lambda *a, **kw: False)
    monkeypatch.setattr("publishers.wiley_library.insert_query.insert_record", lambda *a, **kw: "success")

    # --- Mock S3 ---
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object", lambda *a, **kw: None)
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object_tagging", lambda *a, **kw: None)

    # --- Mock PDF fetching & email extraction ---
    monkeypatch.setattr("publishers.wiley_library.get_pdf_content_for_wiley", lambda doi, landing_url=None: b"%PDF dummy")
    monkeypatch.setattr("publishers.wiley_library.extract_principal_author_and_email", lambda pdf: ("John Doe", "john@example.com"))

    # --- Build a proper namespaced DC record node ---
    DC_NS = "http://purl.org/dc/elements/1.1/"
    DCTERMS_NS = "http://purl.org/dc/terms/"
    PRISM_NS = "http://prismstandard.org/namespaces/basic/2.1/"
    nsmap = {"dc": DC_NS, "dcterms": DCTERMS_NS, "prism": PRISM_NS}

    node = etree.Element(f"{{{DC_NS}}}dc", nsmap=nsmap)
    etree.SubElement(node, f"{{{DC_NS}}}identifier").text = "10.1029/2020av000271"
    etree.SubElement(node, f"{{{DC_NS}}}title").text = "Test Article"
    etree.SubElement(node, f"{{{DC_NS}}}contributor").text = "Jane Smith"
    etree.SubElement(node, f"{{{DC_NS}}}date").text = "2024-01-01"
    etree.SubElement(node, f"{{{DCTERMS_NS}}}issued").text = "2024"
    etree.SubElement(node, f"{{{PRISM_NS}}}url").text = "https://onlinelibrary.wiley.com/doi/10.1029/2020av000271"

    # --- Mock SRU page fetch to return our node ---
    monkeypatch.setattr("publishers.wiley_library._fetch_wiley_page", lambda *a, **kw: ([node], None))

    # --- Call the function ---
    processed_articles, total, page = process_wiley_library(
        pub="wiley",
        method="GET",
        keywords=["climate"],
        api_config={},
        start_page=1,
    )

    # --- Assertions ---
    assert isinstance(processed_articles, list)
    assert total == 1
    # page starts at 1 and increments after processing one SRU batch
    assert page == 2

    rec = processed_articles[0]
    assert rec["doi"] == "10.1029/2020av000271"
    assert rec["title"] == "Test Article"
    assert rec["authors"] == "John Doe"
    assert rec["author_email"] == "john@example.com"



def test_process_wiley_library_real(monkeypatch):
    """
    Real integration test against Wiley SRU.
    Network call is real; DB + S3 operations are mocked.
    """

    # Limit the batch for quicker tests
    monkeypatch.setattr("publishers.wiley_library.MAX_ARTICLES", 2)


    # --- Patch DB & S3 to no-op ---
    monkeypatch.setattr("publishers.wiley_library.select_query.get_records", lambda *a, **kw: False)
    monkeypatch.setattr("publishers.wiley_library.insert_query.insert_record", lambda *a, **kw: "success")
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object", lambda *a, **kw: None)
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object_tagging", lambda *a, **kw: None)

    # --- Patch PDF/email so it skips PDF fetching but still inserts ---
    # monkeypatch.setattr("publishers.wiley_library.get_pdf_content_for_wiley", lambda doi, landing_url=None: b"%PDF fake")
    monkeypatch.setattr("publishers.wiley_library.extract_principal_author_and_email", lambda pdf: ("John Doe", "john@example.com"))

    processed, total, page = process_wiley_library(
        pub="wiley",
        method="GET",
        keywords=["climate"],
        api_config={},
        start_page=1,
    )

    # --- Assertions ---
    assert isinstance(processed, list)
    assert total >= 0
    assert isinstance(page, int)

    if processed:
        first = processed[0]
        assert "doi" in first
        assert "title" in first
        assert "author_email" in first
        print("Sample article:", first["doi"], "-", first["title"])
        print("first record -->", first)


@pytest.mark.real
def test_get_pdf_content_for_wiley_real_download_one_pdf():
    """
    Integration test: download one real Wiley PDF via cloudscraper.
    - Uses a known open-access DOI from AGU (Wiley)
    - Skips gracefully if network or 403 occurs
    """
    
    test_doi = "10.1029/2007gl030025"   # This sample is low size (around 300 kilobytes)

    print(f"\n🔎 Testing real PDF download for DOI: {test_doi}")
    pdf_content = get_pdf_content_for_wiley(test_doi)

    # If PDF not returned (403, network error, etc.), skip rather than fail hard
    if not pdf_content:
        pytest.skip("No PDF content returned — likely paywalled or network-blocked.")

    # Basic sanity checks
    assert isinstance(pdf_content, bytes), "Expected bytes from PDF fetch."
    assert pdf_content.startswith(b"%PDF"), "Response does not start with %PDF header."

    # Optionally write to a temp file (for debugging/manual check)
    tmp_path = os.path.join(tempfile.gettempdir(), f"wiley_test_{test_doi.replace('/', '_')}.pdf")
    with open(tmp_path, "wb") as f:
        f.write(pdf_content)

    print(f"✅ PDF successfully downloaded (size={len(pdf_content)} bytes)")
    print(f"Saved to: {tmp_path}")

