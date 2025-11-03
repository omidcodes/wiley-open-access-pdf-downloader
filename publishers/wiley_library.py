from io import BytesIO
import cloudscraper
from publisher_settings import BATCH_SIZE, MAX_ARTICLES, PUBLISHER_NAME_FOR_DB
from hash_func import hashify
import requests
from PyPDF2 import PdfReader
import re
import time
from lxml import etree
from typing import Any, Dict, List, Optional, Tuple

from utils import save_pdf


# -----------------------------
# Constants / namespaces
# -----------------------------
WILEY_SRU_BASE = "https://onlinelibrary.wiley.com/action/sru"
# Wiley SRU wants browser-like headers to avoid 403
WILEY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://onlinelibrary.wiley.com/",
}
NS = {
    "zs": "http://docs.oasis-open.org/ns/search-ws/sruResponse",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "prism": "http://prismstandard.org/namespaces/basic/2.1/",
}

DOI_CORE_RE = re.compile(r'^(10\.\d{4,9}/\S+?)(?:@|$)')

def clean_doi(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    m = DOI_CORE_RE.match(s)
    return m.group(1) if m else s

# -----------------------------
# PDF + author/email extraction
# -----------------------------
def extract_principal_author_and_email(pdf_content: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract principal author's name and email from a PDF (in-memory).
    Returns (name, email) or (None, None).
    """
    try:
        reader = PdfReader(BytesIO(pdf_content))
        text_parts = []
        for page in reader.pages:
            try:
                page_text = page.extract_text()  # may be None
                if page_text:
                    text_parts.append(page_text)
            except Exception:
                continue
        text = "\n".join(text_parts)
        if not text.strip():
            print("[PDF TEXT] No extractable text")
            return None, None

        # Find emails
        emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
        email: Optional[str] = emails[0] if emails else None

        # Naive name guess near the first email
        name: Optional[str] = None
        if email:
            before_email = text.split(email)[0]
            lines = [l.strip() for l in before_email.splitlines() if l.strip()]
            for line in reversed(lines[-5:]):
                name_matches = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', line)
                if name_matches:
                    name = name_matches[-1]
                    break
            if not name:
                name_matches = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', before_email)
                if name_matches:
                    name = name_matches[-1]

        return name, email
    except Exception as e:
        print(f"[ERROR] While extracting author/email | Error: {e}")
        return None, None


def build_download_pdf_url_from_doi_for_wiley(doi:str) -> str:
    assert isinstance(doi, str)
    return f"https://agupubs.onlinelibrary.wiley.com/doi/pdfdirect/{doi}?download=true"


def get_pdf_content_for_wiley(doi: Optional[str], landing_url: Optional[str] = None) -> Optional[bytes]:
    """
    Try common Wiley endpoints for a PDF; return bytes if found, else None.
    Uses cloudscraper when available to bypass basic bot checks (403).
    """
    # Candidate URLs to probe (order matters: prefer pdfdirect)
    candidates: List[str] = []
    if doi:
        candidates += [
            build_download_pdf_url_from_doi_for_wiley(doi),
        ]
    if landing_url:
        candidates.append(landing_url)
        candidates.append(landing_url + "?download=true")

    session = cloudscraper.create_scraper(
        browser={"custom": "chrome", "platform": "windows", "mobile": False}
    )

    def _is_pdf_response(resp: requests.Response) -> bool:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype:
            return True
        # Fallback: check magic bytes
        return bool(resp.content and resp.content.startswith(b"%PDF"))

    # Try each candidate with a small retry/backoff strategy
    for url in candidates:
        for attempt in range(2):
            try:
                resp = session.get(url, headers=WILEY_HEADERS, timeout=30, allow_redirects=True)
                status = resp.status_code
                ctype = resp.headers.get("Content-Type", "")
                final = resp.url
                print(f"[PDF PROBE] DOI={doi} Attempt={attempt+1} → Status={status} | Type={ctype} | URL={final}")
                if status == 200 and _is_pdf_response(resp):
                    print(f"[PDF FOUND] DOI={doi} Size={len(resp.content)} bytes | Final URL={final}")
                    return resp.content
                # If 403 or 429 or other soft failure, backoff and retry
                if status in (403, 429, 500, 502, 503, 504):
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                # non-PDF 200 or other status -> break retry loop and try next candidate
                break
            except Exception as e:
                print(f"[PDF ERROR] DOI={doi} Attempt={attempt+1} | URL={url} | Error={e}")
                time.sleep(0.5 * (2 ** attempt))
                continue
    # Nothing worked
    return None

# -----------------------------
# SRU(Search/Retrieve via URL) paging + parsing
# -----------------------------
def _node_text(node: "etree._Element", xp: str) -> Optional[str]:
    vals = node.xpath(xp, namespaces=NS)
    if not vals:
        return None
    v = vals[0]
    return (v.text if hasattr(v, "text") else str(v)).strip() or None

def _node_texts(node: "etree._Element", xp: str) -> List[str]:
    out: List[str] = []
    for v in node.xpath(xp, namespaces=NS):
        if hasattr(v, "text") and v.text and v.text.strip():
            out.append(v.text.strip())
        elif isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out

def _fetch_wiley_page(
    cql: str,
    start_record: int = 1,
    maximum_records: int = 20,
    retries: int = 4,
    pause: float = 0.5
) -> Tuple[List["etree._Element"], Optional[int]]:
    """
    Fetch one 'page' from Wiley SRU and return (record_nodes, next_record_position or None).
    """
    params = {
        "operation": "searchRetrieve",
        "version": "2.0",
        "recordSchema": "info:srw/cql-context-set/11/prism-v2.1",
        "query": cql,
        "maximumRecords": min(int(maximum_records), 20),
        "startRecord": int(start_record),
    }
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = requests.get(WILEY_SRU_BASE, params=params, headers=WILEY_HEADERS, timeout=30)
            if r.status_code == 200:
                root = etree.fromstring(r.content)
                nodes: List["etree._Element"] = root.xpath(".//zs:recordData/dc:dc", namespaces=NS)  # type: ignore
                nxt = root.xpath("string(.//zs:nextRecordPosition)", namespaces=NS)
                nxt = nxt.strip() if isinstance(nxt, str) else ""
                next_pos = int(nxt) if nxt.isdigit() else None
                return nodes, next_pos
            if r.status_code in (403, 429, 500, 502, 503, 504):
                time.sleep((2 ** attempt) * pause)
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            time.sleep((2 ** attempt) * pause)
            continue
    if last_exc:
        raise last_exc
    return [], None

def _normalise_record(node: "etree._Element") -> Dict[str, Any]:
    abstracts = _node_texts(node, "./dc:description")
    doi_raw = _node_text(node, "./dc:identifier")
    doi = clean_doi(doi_raw)
    title = _node_text(node, "./dc:title")
    authors = _node_texts(node, "./dc:contributor")
    published_date = _node_text(node, "./dc:date")
    issued_year = _node_text(node, "./dcterms:issued")
    journal = _node_text(node, "./dcterms:isPartOf")
    volume = _node_text(node, "./dc:rft.volume")
    issue = _node_text(node, "./dc:rft.issue")
    spage = _node_text(node, "./dc:rft.spage")
    landing = _node_text(node, "./prism:url")
    subjects = _node_texts(node, "./dc:subject")

    rec: Dict[str, Any] = {
        "doi": doi,
        "doi_raw": doi_raw,
        "title": title,
        "abstract": " ".join(abstracts) if abstracts else None,
        "authors": authors,
        "published_date": published_date,
        "issued_year": issued_year,
        "journal": journal,
        "volume": volume,
        "issue": issue,
        "start_page": spage,
        "landing_url": landing,
        "subjects": subjects
    }
    return rec


def is_openaccess_pdf(doi: str, timeout: int = 15) -> Optional[bool]:
    """
    Check if a Wiley DOI corresponds to an open-access PDF (using cloudscraper).
    Returns:
        True  → open-access PDF (accessible, content-type is PDF)
        False → exists but not open-access (403, HTML, etc.)
        None  → network or unexpected error
    """
    url = build_download_pdf_url_from_doi_for_wiley(doi)
    scraper = cloudscraper.create_scraper(
        browser={"custom": "chrome", "platform": "windows", "mobile": False}
    )

    try:
        # First attempt: use HEAD (lightweight)
        resp = scraper.request("HEAD", url, headers=WILEY_HEADERS, timeout=timeout, allow_redirects=True)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        status = resp.status_code

        if status == 200 and "pdf" in ctype:
            print(f"✅ Open-access PDF detected for DOI: {doi}")
            return True

        # Some servers block HEAD — fallback to streamed GET
        if status in (403, 404, 405) or not ctype:
            resp = scraper.get(url, headers=WILEY_HEADERS, stream=True, timeout=timeout, allow_redirects=True)
            gtype = (resp.headers.get("Content-Type") or "").lower()
            if resp.status_code == 200 and "pdf" in gtype:
                print(f"✅ Open-access PDF confirmed for DOI: {doi}")
                return True
            else:
                print(f"❌ SKIP : Not open-access or restricted for DOI: {doi} ({resp.status_code})")
                return False

        if "html" in ctype or status == 403:
            print(f"❌ SKIP : Paywalled or restricted access for DOI: {doi}")
            return False

        print(f"⚠️ Unexpected response for DOI: {doi} → {status}, {ctype}")
        return False

    except Exception as e:
        print(f"[NETWORK ERROR] DOI={doi} | {e}")
        return None


# -----------------------------
# Public adapter entry point
# -----------------------------
def process_wiley_library(
    keywords: List[str],
    start_page: int = 1
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Returns: (processed_articles, total_processed, next_page_pointer_or_-1)
    """
    t0 = time.time()
    print("🚀 [START] Processing Wiley Library via SRU...")
    print(f"[CONFIG] MAX_ARTICLES={MAX_ARTICLES} | BATCH_SIZE={BATCH_SIZE} | Keywords={keywords}")

    processed_articles: List[Dict[str, Any]] = []
    total_processed = 0

    seen_hashes = set()

    parts: List[str] = []
    for kw in keywords:
        kw_esc = kw.replace('"', '\\"')
        parts.append(f'dc.title="{kw_esc}"')
        parts.append(f'dc.description="{kw_esc}"')
        parts.append(f'dc.subject="{kw_esc}"')
    cql_query = f'({" OR ".join(parts)}) AND dc.type=article' if parts else 'dc.type=article'

    page: int = start_page if start_page > 0 else 1

    next_pos: Optional[int] = 1 if start_page < 1 else (start_page - 1) * BATCH_SIZE + 1

    while total_processed < MAX_ARTICLES and next_pos:
        print(f"[PAGE] Fetching SRU records → startRecord={next_pos} | batch_size={BATCH_SIZE}")
        nodes, next_pos = _fetch_wiley_page(
            cql=cql_query,
            start_record=next_pos,
            maximum_records=BATCH_SIZE,
            retries=4,
            pause=0.5
        )
        if not nodes:
            print(f"[PAGE] No records found for startRecord={next_pos}")
            break
        
        open_access_nodes = []
        print("Filtering open-access resources only --> ")
        for node in nodes:
            try:
                record = _normalise_record(node)
                doi = record["doi"]
                if not doi:
                    continue
                if is_openaccess_pdf(doi=doi):
                    open_access_nodes.append(node)
            except Exception as e:
                print(f"[ERROR] While processing record | Error: {e}")
                continue

        for node in open_access_nodes:
            try:
                record = _normalise_record(node)
                doi = record["doi"]
                title = record["title"] or ""
                year_str = (record["published_date"] or "")[:4] or (record["issued_year"] or "")
                calc_hash = hashify(f"{doi} {title}")
                
                try:
                    year = int(year_str)
                except ValueError:
                    year = None
                
                # NEW: skip duplicates within the same run
                if calc_hash in seen_hashes:
                    continue
                seen_hashes.add(calc_hash)

                # Attempt to retrieve PDF & extract corresponding author/email
                pdf_content = get_pdf_content_for_wiley(doi, landing_url=record["landing_url"])
                if not pdf_content:
                    print(f"[SKIP] No PDF (likely paywalled) | DOI={doi}")
                    continue

                principal_author, author_email = extract_principal_author_and_email(pdf_content)
                if not author_email:
                    print(f"[SKIP] No author email found | DOI={doi}")
                    continue

                
                wrapper_keywords = '_'.join(keywords).lower() if keywords else "all"
                doi_suffix = (doi or "no-doi").split('/')[-1]
                pdf_name :str = f"{PUBLISHER_NAME_FOR_DB}_{wrapper_keywords}_{doi_suffix}.pdf"

                save_pdf(
                    pdf_name=pdf_name,
                    pdf_content=pdf_content,
                )

                subjects_list = record.get("subjects", [])
                topic = subjects_list[0] if subjects_list else ""

                # # Prepare DB record (align fields with other adapters)
                # article_data = {
                #     'title': title,
                #     'doi': doi,
                #     'year': year,
                #     'source_url': build_download_pdf_url_from_doi_for_wiley(doi=doi) or "",  # download URL

                #     'landing_url': record.get("landing_url") or "", # landing page URL which is not a direct download URL.
                #     'calc_hash': calc_hash,
                #     'authors': principal_author,
                #     'author_email': author_email,
                #     'keywords': ','.join(subjects_list) if isinstance(subjects_list, list) else "",

                #     'journal_name': PUBLISHER_NAME_FOR_DB,
                #     'publisher_name': PUBLISHER_NAME_FOR_DB,

                #     # Map 'topic' to first subject if available
                #     'topic': topic,
                # }

                # insert_result = insert_query.insert_record('INSERT', **article_data)
                # if insert_result == "success":
                #     processed_articles.append(article_data)
                #     total_processed += 1
                #     print(f"[DB INSERT ✅] DOI={doi}")
                # else:
                #     print(f"[DB INSERT ❌] DOI={doi}")

                if total_processed >= MAX_ARTICLES:
                    break

            except Exception as e:
                print(f"[ERROR] While processing record | Error: {e}")
                continue

        if total_processed >= MAX_ARTICLES:
            break

        # One SRU batch processed successfully → advance *page counter* by 1
        page += 1
        print(f"[SUMMARY] Page processed. Total so far: {total_processed}/{MAX_ARTICLES}")

    verify_processing(processed_articles)

    elapsed = round(time.time() - t0, 2)
    print(f"✅ [DONE] Processed {total_processed} open-access articles in {elapsed}s (last page={page})")

    return processed_articles, total_processed, page


def verify_processing(processed_articles: List[Dict[str, Any]]) -> None:
    for article in processed_articles:
        print(f"[VERIFY] DOI={article['doi']}")
        print(f"   ↳ Hash={article['calc_hash']}")

def format_author_name(author: str) -> str:
    if ',' in author:
        last_name, first_name = author.split(',', 1)
        return f"{last_name.strip()} {first_name.strip()}"
    return author
