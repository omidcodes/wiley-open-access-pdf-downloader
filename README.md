# Wiley Open-Access PDF Downloader

Local-only tool to query the **Wiley Online Library SRU** endpoint by keyword(s), filter **Open Access** results, download the **PDFs to `./downloads/`**, and heuristically extract the principal author/email from the PDF text.

- ✅ Pure local filesystem output
- ✅ Pytest unit tests

---

## Features

- 🔎 Keyword search via Wiley SRU with browser-like headers (helps reduce 403s)
- 🧭 Pagination via SRU `nextRecordPosition`
- ✅ Open-Access filtering
- 📄 PDF download + simple heuristic extraction of **author name** and **email** from text
- 💾 Files saved under `./downloads/` at the project root
- 🧪 Tests that mock network/IO (no real HTTP, no DB)

---

## Requirements

- Python 3.9+
- A virtual environment is recommended

Install dependencies:

```bash
pip install -r requirements.txt
````

---

## Run locally

Basic run:

```bash
python run_local.py --keywords climate action
```

Optional start page:

```bash
python run_local.py --keywords biodiversity conservation --start-page 1
```

Note: You can adjust batch size and total items by editing `publisher_settings.py` → `BATCH_SIZE`, `MAX_ARTICLES` .

You’ll see logs like:

```
🚀 [START] Processing Wiley Library via SRU...
[CONFIG] MAX_ARTICLES=... | BATCH_SIZE=... | Keywords=['climate', 'action']
[PAGE] Fetching SRU records → startRecord=1 | batch_size=...
Filtering open-access resources only -->
[LOCAL : PDF saved] .../downloads/WileyLibrary_<hash>.pdf | size=... bytes
[SUMMARY] Page processed. Total so far: 1/...
✅ [DONE] Processed 1 open-access articles in 0.8s (last page=2)
```

All PDFs land in:

```
./downloads/<filename>.pdf
```

---

## How it works (high level)

1. Build a Wiley SRU query for your keywords.
2. Fetch a page of records; normalize essential fields (DOI, title, landing URL, subjects, year).
3. Keep only Open-Access items.
4. Resolve a PDF URL and download it (using `cloudscraper/requests`).
5. Extract a principal author/email (best-effort heuristic).
6. Save the PDF to `./downloads/` using `utils.save_pdf()`.

---

## Testing

Run the test suite:

```bash
pytest -v -s
```

Tests use `monkeypatch`/mocks so:

* No network calls are made
* No DB is required
* File writes go to temporary locations during tests


---

## License

MIT
