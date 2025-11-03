#!/usr/bin/env python3
"""
Wiley SRU fetcher (standalone, constants version)

- DO not forget to change CONFIGURATION CONSTANTS (especially `CQL_QUERY`)

- Uses SRU 2.0 with PRISM/DC schema
- Proper headers to avoid 403
- Paginates via nextRecordPosition
- Normalises records and cleans decorated DOIs
- Prints to stdout and optionally writes JSONL
"""

import json
import re
import time
from typing import Dict, Iterable, Optional

import requests
from lxml import etree

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from publishers.wiley_library import build_download_pdf_url_from_doi_for_wiley

# =======================
# CONFIGURATION CONSTANTS
# =======================
CQL_QUERY = 'cql.anywhere=climate AND dc.type=article'  # WE CAN CHANGE THIS QUERY

LIMIT = 10           # total records to fetch
PAGE_SIZE = 20       # <=20 (Wiley max)
START = 1            # starting record
PAUSE = 0.5          # seconds between requests
OUT_FILE = None      # e.g. "wiley_out.jsonl" or None to disable
# =======================

BASE = "https://onlinelibrary.wiley.com/action/sru"

NS = {
    "zs": "http://docs.oasis-open.org/ns/search-ws/sruResponse",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "prism": "http://prismstandard.org/namespaces/basic/2.1/",
}

HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://onlinelibrary.wiley.com/",
}

DOI_CORE_RE = re.compile(r'^(10\.\d{4,9}/\S+?)(?:@|$)')

def clean_doi(raw: Optional[str]) -> Optional[str]:
    """Extract the core DOI (strip Wiley 'decorations' after '@')."""
    if not raw:
        return None
    s = raw.strip()
    m = DOI_CORE_RE.match(s)
    return m.group(1) if m else s

def _text(node, xp: str) -> Optional[str]:
    vals = node.xpath(xp, namespaces=NS)
    if not vals:
        return None
    val = vals[0]
    return (val.text if hasattr(val, "text") else str(val)).strip() or None

def _texts(node, xp: str):
    return [
        (v.text if hasattr(v, "text") else str(v)).strip()
        for v in node.xpath(xp, namespaces=NS)
        if (hasattr(v, "text") and v.text and v.text.strip()) or (isinstance(v, str) and v.strip())
    ]

def normalise_from_node(node) -> Dict:
    """Turn a <dc:dc> node into our normalised record."""
    abstracts = _texts(node, "./dc:description")
    
    rec = {
        "source": "Wiley SRU",
        "doi_raw": _text(node, "./dc:identifier"),
        "title": _text(node, "./dc:title"),
        "abstract": " ".join(abstracts) if abstracts else None,
        "authors": _texts(node, "./dc:contributor"),
        "published_date": _text(node, "./dc:date"),
        "issued_year": _text(node, "./dcterms:issued"),
        "journal": _text(node, "./dcterms:isPartOf"),
        "volume": _text(node, "./dc:rft.volume"),
        "issue": _text(node, "./dc:rft.issue"),
        "start_page": _text(node, "./dc:rft.spage"),
        "landing_url": _text(node, "./prism:url"),
    }

    doi = clean_doi(rec["doi_raw"])
    rec["doi"] = clean_doi(rec["doi_raw"])
    rec["source_url"] = build_download_pdf_url_from_doi_for_wiley(doi=doi)

    return rec

def fetch_wiley(
    cql: str,
    start: int = 1,
    page_size: int = 20,
    limit: int = 100,
    pause: float = 0.5,
    max_retries: int = 4,
) -> Iterable[Dict]:
    """Generator that yields normalised records from Wiley SRU for the given CQL query."""
    got = 0
    next_pos = start

    while got < limit and next_pos:
        params = {
            "operation": "searchRetrieve",
            "version": "2.0",
            "recordSchema": "info:srw/cql-context-set/11/prism-v2.1",
            "query": cql,
            "maximumRecords": min(page_size, 20),
            "startRecord": next_pos,
        }

        # simple retry/backoff for 403/429/5xx
        last_exc = None
        for attempt in range(max_retries):
            try:
                r = requests.get(BASE, params=params, headers=HDRS, timeout=30)
                if r.status_code == 200:
                    break
                if r.status_code in (403, 429, 500, 502, 503, 504):
                    time.sleep((2 ** attempt) * 0.5)
                    continue
                r.raise_for_status()
            except requests.RequestException as e:
                last_exc = e
                time.sleep((2 ** attempt) * 0.5)
                continue
        else:
            if last_exc:
                raise last_exc
            r.raise_for_status()

        root = etree.fromstring(r.content)

        # Yield records
        nodes = root.xpath(".//zs:recordData/dc:dc", namespaces=NS)
        for node in nodes:
            yield normalise_from_node(node)
            got += 1
            if got >= limit:
                break

        # Move to next page via Wiley's pointer
        nxt = root.xpath("string(.//zs:nextRecordPosition)", namespaces=NS)
        nxt = nxt.strip() if isinstance(nxt, str) else ""
        next_pos = int(nxt) if nxt.isdigit() else None

        time.sleep(pause)

def main():
    out_f = open(OUT_FILE, "w", encoding="utf-8") if OUT_FILE else None
    try:
        for i, rec in enumerate(
            fetch_wiley(
                cql=CQL_QUERY,
                start=START,
                page_size=PAGE_SIZE,
                limit=LIMIT,
                pause=PAUSE,
            ),
            1,
        ):
            print(f"{i:>4} -> {rec.get('doi')} {rec.get('published_date')}  '{rec.get('title')}'  {rec.get("source_url")}")
            if out_f:
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    finally:
        if out_f:
            out_f.close()

if __name__ == "__main__":
    main()
