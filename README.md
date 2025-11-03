## README.md

# Wiley Open-Access PDF Downloader

Query the **Wiley Online Library SRU** endpoint by keyword(s), filter for **Open Access** items, download the **PDFs locally**, and (optionally) store article metadata in a PostgreSQL table.

This is a local, AWS-free version of the original Lambda project. It keeps the Wiley SRU logic, PDF parsing (principal author + email heuristic), and optional Postgres insert—but removes AWS Secrets Manager and S3. PDFs are written to your filesystem.

---

## Features

* 🔎 Keyword search via Wiley SRU (with robust headers to avoid 403s)
* 🧭 Pagination through `nextRecordPosition`
* ✅ Open-Access filtering
* 📄 PDF download + first-page extraction of **principal author** and **email** (heuristic)
* 🗃️ Optional Postgres insert into `web_crawler_journals` via `tiquu_pg/insert_query.py`
* 💾 Local filesystem output (no AWS)

---

## Project Structure (key files)

```
publishers/
  wiley_library.py       # SRU fetch, OA filter, PDF download, author/email extraction
tiquu_pg/
  config.py              # Local DB config loader (env or db.local.yaml)
  insert_query.py        # Insert into web_crawler_journals
  select_query.py        # Duplicate check helpers
config_utils.py          # Returns api_config (Wiley needs none)
hash_func.py             # SHA256 helper for hash_value
run_local.py             # Local entry point (no AWS)
tests/                   # Pytest tests/mocks
```

**Removed:** `lambda_function.py`, `crawler_init.py` (AWS Lambda / SSM / Secrets Manager), S3 upload.

---

## Requirements

* Python 3.9+ (tested with 3.10+ recommended)
* `pip`/`venv`
* A local Postgres instance **if** you want DB inserts (optional)

Install Python deps:

```bash
pip install -r requirements.txt
```

---

## Configuration

### 1) Downloads folder

By default PDFs are saved under:

```
./downloads/<PublisherName>/<joined_keywords>/<doi_suffix>.pdf
```

You can override the root via environment variable:

```bash
export DOWNLOAD_DIR=/absolute/path/to/downloads
```

### 2) Database (optional)

If you want metadata inserts into Postgres, configure one of:

* **Environment variables (preferred):**

  ```
  PGHOST=localhost
  PGPORT=5432
  PGDATABASE=your_db
  PGUSER=your_user
  PGPASSWORD=your_password
  ```

* **Or** create `db.local.yaml`:

  ```yaml
  postgresql:
    host: localhost
    port: 5432
    dbname: your_db
    user: your_user
    password: your_password
  ```

> The loader in `tiquu_pg/config.py` uses env vars first, then `db.local.yaml`.

---

## Run locally

Basic run with two keywords:

```bash
python run_local.py --keywords climate action
```

Choose the SRU start page (rarely needed):

```bash
python run_local.py --keywords biodiversity conservation --start-page 1
```

You’ll see progress logs like:

```
🚀 [START] Processing Wiley Library via SRU...
[PAGE] Fetching SRU records → startRecord=1 | batch_size=...
[LOCAL : PDF saved] downloads/Wiley Library/climate_action/2020av000271.pdf | size=... bytes | DOI=10.1029/2020av000271
[DB INSERT ✅] DOI=10.1029/2020av000271
...
✅ Done. Inserted/processed: 25. Next page pointer: 51
```

---

## How it works (high level)

1. **SRU query** is constructed against:

   ```
   https://onlinelibrary.wiley.com/action/sru
   ```

   using DC/PRISM metadata; keywords are applied to `dc.title` and `dc.description`.

2. **Open Access filter** is applied from the SRU response (and by trying the PDF URL).

3. **PDF download** uses `cloudscraper/requests` with browsery headers to reduce 403s.

4. **Author/email extraction** parses the first page text with `PyPDF2` and a simple regex heuristic.

5. **Dedup check** compares a SHA-256 hash of `"{doi} {title}"` via `tiquu_pg/select_query.py`.

6. **Insert (optional)** writes a row to `web_crawler_journals` via `tiquu_pg/insert_query.py`.

---

## Notes & Tips

* **Wiley SRU quirks**: we send Chrome-like headers; short pauses are built-in to avoid rate spikes.
* **Heuristic email extraction**: it’s pragmatic, not perfect. It scans for an email on the first page and tries to capture the preceding name.
* **DB schema**: `insert_query.py` expects a table named `web_crawler_journals` with fields seen in that file (e.g., `hash_value, journal_name, doi, authors, author_email, title, source_url, keywords, topic, publisher_name, year`).
* **No API key**: for Wiley, `config_utils.get_api_config()` returns an empty key by design.
* **Testing**: several tests mock DB and network calls; you can run `pytest`.

---

## License

MIT (you can change this to suit your needs).

---

## Changelog

* **v2 (local)**: Removed AWS (Lambda, SSM/SecretsManager, S3). Added local runner and filesystem output.
* **v1 (legacy)**: AWS Lambda + S3 uploads.

---

If you want, I can also generate the `run_local.py` and `db.local.yaml.example` files exactly as above and drop them into your repo structure—just say the word.
