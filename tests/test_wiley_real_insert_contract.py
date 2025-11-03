import pytest
from lxml import etree


@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize(
    "doi,title,note",
    [
        (
            "10.1002/ird.2336",
            "Applying Climate Adaptation Strategies for Improvement of Management Indexes of a River–Reservoir Irrigation System",
            "HTML skip",
        ),
        (
            "10.1002/env.2153",
            "Statistical problems in the probabilistic prediction of climate change",
            "HTML skip",
        ),
        (
            "10.1029/2007gl030025",
            "Assessment of the use of current climate patterns to evaluate regional enhanced greenhouse response patterns of climate models",
            "PDF OK",
        ),
        (
            "10.1002/grl.50386",
            "Global modes of climate variability",
            "PDF OK",
        ),
    ],
)
def test_process_wiley_library_real_insert_kwargs(monkeypatch, doi, title, note):
    """
    Runs process_wiley_library in 'real mode' for known DOIs.
    Just ensures no crash and prints diagnostic info.
    """

    from publishers.wiley_library import process_wiley_library

    # --- capture insert calls
    inserted_records = []

    def fake_insert_record(action, **kwargs):
        inserted_records.append(kwargs)
        return "success"

    monkeypatch.setattr("publishers.wiley_library.insert_query.insert_record", fake_insert_record)
    monkeypatch.setattr("publishers.wiley_library.select_query.get_records", lambda *a, **kw: False)
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object", lambda *a, **kw: None)
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object_tagging", lambda *a, **kw: None)

    # Run the function (real SRU but mocked DB and S3)
    processed_articles, total, page = process_wiley_library(
        pub="wiley",
        method="GET",
        keywords=[doi],
        api_config={},
        start_page=1,
    )

    # if inserted_records:
    #     print(f"✅ Inserted record for DOI {doi}")
    # else:
    #     print(f"⚠️ No insert for DOI {doi} ({note}) — nothing to validate.")

    assert True  # don't fail real runs by default


def test_process_wiley_library_force_insert(monkeypatch):
    """
    Force an insert path by mocking SRU results + PDF + email extraction.
    This lets us see and assert the insert_record(**kwargs) contract.
    """
    inserted = []

    # --- capture insert kwargs
    def fake_insert_record(action, **kwargs):
        inserted.append(kwargs)
        return "success"

    # --- mocks: DB + S3
    monkeypatch.setattr("publishers.wiley_library.insert_query.insert_record", fake_insert_record)
    monkeypatch.setattr("publishers.wiley_library.select_query.get_records", lambda *a, **kw: False)
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object", lambda *a, **kw: None)
    monkeypatch.setattr("publishers.wiley_library.s3_client.put_object_tagging", lambda *a, **kw: None)

    # --- mock PDF + email
    monkeypatch.setattr("publishers.wiley_library.get_pdf_content_for_wiley", lambda *a, **kw: b"%PDF-1.4 dummy")
    monkeypatch.setattr(
        "publishers.wiley_library.extract_principal_author_and_email",
        lambda *a, **kw: ("Jane Smith", "jane@example.com"),
    )

    # --- fabricate one SRU record node (namespaced DC)
    DC_NS = "http://purl.org/dc/elements/1.1/"
    DCTERMS_NS = "http://purl.org/dc/terms/"
    PRISM_NS = "http://prismstandard.org/namespaces/basic/2.1/"
    nsmap = {"dc": DC_NS, "dcterms": DCTERMS_NS, "prism": PRISM_NS}

    node = etree.Element(f"{{{DC_NS}}}dc", nsmap=nsmap)
    etree.SubElement(node, f"{{{DC_NS}}}identifier").text = "10.1029/2007GL030025"
    etree.SubElement(node, f"{{{DC_NS}}}title").text = "Assessment of the use of current climate patterns..."
    etree.SubElement(node, f"{{{DC_NS}}}contributor").text = "Penny Whetton"
    etree.SubElement(node, f"{{{DC_NS}}}date").text = "2007-07-17"
    etree.SubElement(node, f"{{{DCTERMS_NS}}}issued").text = "2007"
    etree.SubElement(node, f"{{{PRISM_NS}}}url").text = "https://onlinelibrary.wiley.com/doi/10.1029/2007GL030025"
    etree.SubElement(node, f"{{{DC_NS}}}subject").text = "climate change"
    etree.SubElement(node, f"{{{DC_NS}}}subject").text = "modeling"

    # --- make SRU return our node
    monkeypatch.setattr("publishers.wiley_library._fetch_wiley_page", lambda *a, **kw: ([node], None))

    # --- run
    from publishers.wiley_library import process_wiley_library
    processed, total, page = process_wiley_library(
        pub="wiley",
        method="GET",
        keywords=["anything"],  # ignored because we patched SRU
        api_config={},
        start_page=1,
    )

    # --- verify & print missing/empty keys (for debugging)
    assert inserted, "Expected one insert_record call"

    record = inserted[0]
    required = {
        "calc_hash", "journal_name", "doi", "authors", "author_email",
        "title", "source_url", "keywords", "topic", "publisher_name", "year",
    }

    def _is_empty(v):
        return v is None or (isinstance(v, str) and v.strip() == "")

    missing_or_empty = sorted([k for k in required if k not in record or _is_empty(record[k])])
    extra = sorted(set(record.keys()) - required)

    print("\n—— insert_record kwargs (sorted) ——")
    for k in sorted(record.keys()):
        v = record[k]
        s = str(v)
        if len(s) > 160:
            s = s[:160] + "…"
        print(f"  {k:<15} = {s}")

    if missing_or_empty:
        print(f"\n⚠️ Missing/empty required keys: {missing_or_empty}")
    if extra:
        print(f"ℹ️ Extra (non-required) keys present: {extra}")

    # all required keys must exist (and not empty except topic)
    assert "topic" in record
    missing_or_empty = [k for k in missing_or_empty if k != "topic"]
    assert not missing_or_empty, f"Missing/empty keys: {missing_or_empty}"
